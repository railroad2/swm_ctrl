#!/usr/bin/env python3

"""
test_ws.py

WebSocket client-side protocol test for the split gateway.

Current gateway layout
----------------------
- Control: ws://HOST:8765 (source-IP restricted)
- Monitor: ws://HOST:8766 (public/read-only)

Default behavior
----------------
- Run the full core test suite
- Use compact summary output
- Print clear PASS / FAIL results
- Print final success/failure counts

Verbose mode
------------
- Use --verbose to print raw JSON traffic
"""

import argparse
import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import websockets


VERBOSE = False


@dataclass
class TestResult:
    """Store one test outcome."""
    name: str
    passed: bool
    detail: str = ""


def pretty(obj: Any) -> str:
    """Return pretty JSON string."""
    return json.dumps(obj, indent=2, ensure_ascii=False)


def print_verbose(title: str, content: Any) -> None:
    """Print detailed content in verbose mode only."""
    if not VERBOSE:
        return

    print(f"\n{title}")
    if isinstance(content, str):
        print(content)
    else:
        print(pretty(content))


def summarize(obj: Dict[str, Any]) -> str:
    """Build compact one-line summary for JSON payload."""
    parts = []

    if "ok" in obj:
        parts.append(f"ok={obj['ok']}")

    if "event" in obj:
        parts.append(f"event={obj['event']}")

    if "cmd" in obj:
        parts.append(f"cmd={obj['cmd']}")

    if "which" in obj:
        parts.append(f"which={obj['which']}")

    if "path" in obj:
        parts.append(f"path={obj['path']}")

    if "channel" in obj:
        parts.append(f"channel={obj['channel']}")

    if "cached" in obj:
        parts.append(f"cached={obj['cached']}")

    if "error" in obj:
        parts.append(f"error={obj['error']}")

    data = obj.get("data")
    if isinstance(data, dict):
        pins = data.get("pins")
        present = data.get("present")
        if isinstance(pins, list):
            parts.append(f"pins={len(pins)}")
        if isinstance(present, list):
            parts.append(f"present={len(present)}")

    if isinstance(obj.get("pins"), list):
        parts.append(f"pins={len(obj['pins'])}")

    if isinstance(obj.get("present"), list):
        parts.append(f"present={len(obj['present'])}")

    return " ".join(parts) if parts else str(obj)


async def recv_json(ws, timeout: Optional[float] = 5.0) -> Dict[str, Any]:
    """Receive one JSON object from websocket."""
    if timeout is None:
        raw = await ws.recv()
    else:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)

    obj = json.loads(raw)

    if not isinstance(obj, dict):
        raise RuntimeError("received JSON is not an object")

    if VERBOSE:
        print("\n<<< RAW")
        print(raw)
        print("\n<<< JSON")
        print(pretty(obj))
    else:
        print(f"    <<< {summarize(obj)}")

    return obj


async def send_json(ws, payload: Dict[str, Any]) -> None:
    """Send one JSON object to websocket."""
    if VERBOSE:
        print("\n>>> JSON")
        print(pretty(payload))
    else:
        print(f"    >>> {summarize(payload)}")

    await ws.send(json.dumps(payload))


async def open_ws(uri: str):
    """Open websocket and receive initial hello."""
    print(f"  CONNECT {uri}")
    ws = await websockets.connect(uri)
    hello = await recv_json(ws)
    return ws, hello


async def test_monitor_basic(monitor_uri: str) -> TestResult:
    """Test basic /monitor commands."""
    name = "monitor-basic"

    try:
        ws, hello = await open_ws(monitor_uri)

        try:
            if hello.get("event") != "connected":
                return TestResult(name, False, "missing connected hello")

            await send_json(ws, {"gateway": "ping"})
            ping_resp = await recv_json(ws)
            if ping_resp.get("event") != "gateway_pong":
                return TestResult(name, False, "gateway ping failed")

            await send_json(ws, {"gateway": "map"})
            map_resp = await recv_json(ws)
            if map_resp.get("event") != "map":
                return TestResult(name, False, "map event missing")
            if not isinstance(map_resp.get("map"), dict):
                return TestResult(name, False, "map payload missing")

            await send_json(ws, {"gateway": "get"})
            get_resp = await recv_json(ws)
            if get_resp.get("event") != "get":
                return TestResult(name, False, "get event missing")
            if not isinstance(get_resp.get("data", {}).get("pins"), list):
                return TestResult(name, False, "get pins missing")

            await send_json(ws, {"gateway": "subscribe"})
            snapshot = await recv_json(ws)
            subscribed = await recv_json(ws)

            if snapshot.get("event") != "pinstat_snapshot":
                return TestResult(name, False, "subscribe did not send snapshot first")
            if subscribed.get("event") != "subscribed":
                return TestResult(name, False, "subscribe ack missing")

            await send_json(ws, {"gateway": "unsubscribe"})
            unsub_resp = await recv_json(ws)
            if unsub_resp.get("event") != "unsubscribed":
                return TestResult(name, False, "unsubscribe ack missing")

            return TestResult(name, True, "monitor commands OK")

        finally:
            await ws.close()

    except Exception as exc:
        return TestResult(name, False, str(exc))


async def test_monitor_reject_control(monitor_uri: str) -> TestResult:
    """Verify /monitor rejects control command."""
    name = "monitor-reject-control"

    try:
        ws, _ = await open_ws(monitor_uri)

        try:
            await send_json(ws, {"cmd": "ON", "pins": [0]})
            resp = await recv_json(ws)

            if resp.get("ok") == 0:
                return TestResult(name, True, "monitor rejected control command")

            return TestResult(name, False, "monitor accepted control command")

        finally:
            await ws.close()

    except Exception as exc:
        return TestResult(name, False, str(exc))


async def test_control_basic(control_uri: str) -> TestResult:
    """Test basic /control commands."""
    name = "control-basic"

    try:
        ws, hello = await open_ws(control_uri)

        try:
            if hello.get("event") != "connected":
                return TestResult(name, False, "missing connected hello")

            await send_json(ws, {"cmd": "PING"})
            ping_resp = await recv_json(ws)
            if ping_resp.get("ok") != 1:
                return TestResult(name, False, "Pico ping failed")

            await send_json(ws, {"cmd": "PINSTAT", "which": "ALL"})
            pin_resp = await recv_json(ws)
            if pin_resp.get("cmd") != "PINSTAT":
                return TestResult(name, False, "PINSTAT response missing")
            if not isinstance(pin_resp.get("pins"), list):
                return TestResult(name, False, "PINSTAT pins missing")

            await send_json(ws, {"cmd": "PCFSTAT", "which": "ALL"})
            pcf_resp = await recv_json(ws)
            if pcf_resp.get("cmd") != "PCFSTAT":
                return TestResult(name, False, "PCFSTAT response missing")
            if not isinstance(pcf_resp.get("present"), list):
                return TestResult(name, False, "PCFSTAT present missing")

            return TestResult(name, True, "control commands OK")

        finally:
            await ws.close()

    except Exception as exc:
        return TestResult(name, False, str(exc))


async def test_control_reject_gateway(control_uri: str) -> TestResult:
    """Verify /control rejects gateway command."""
    name = "control-reject-gateway"

    try:
        ws, _ = await open_ws(control_uri)

        try:
            await send_json(ws, {"gateway": "subscribe"})
            resp = await recv_json(ws)

            if resp.get("ok") == 0:
                return TestResult(name, True, "control rejected gateway command")

            return TestResult(name, False, "control accepted gateway command")

        finally:
            await ws.close()

    except Exception as exc:
        return TestResult(name, False, str(exc))


async def test_event_flow(
    control_uri: str,
    monitor_uri: str,
    pin: int,
) -> TestResult:
    """Verify ON/OFF on /control produces monitor updates on /monitor."""
    name = "event-flow"

    try:
        mon_ws, _ = await open_ws(monitor_uri)
        ctl_ws, _ = await open_ws(control_uri)

        try:
            await send_json(mon_ws, {"gateway": "subscribe"})
            snapshot = await recv_json(mon_ws)
            subscribed = await recv_json(mon_ws)

            if snapshot.get("event") != "pinstat_snapshot":
                return TestResult(name, False, "missing initial snapshot")
            if subscribed.get("event") != "subscribed":
                return TestResult(name, False, "missing subscribed ack")

            await send_json(ctl_ws, {"cmd": "ON", "pins": [pin]})
            ctl_on = await recv_json(ctl_ws)
            mon_on = await recv_json(mon_ws, timeout=5.0)

            if ctl_on.get("ok") != 1:
                return TestResult(name, False, "ON command failed")
            if mon_on.get("event") != "pinstat_update":
                return TestResult(name, False, "missing monitor update after ON")

            await send_json(ctl_ws, {"cmd": "OFF", "pins": [pin]})
            ctl_off = await recv_json(ctl_ws)
            mon_off = await recv_json(mon_ws, timeout=5.0)

            if ctl_off.get("ok") != 1:
                return TestResult(name, False, "OFF command failed")
            if mon_off.get("event") != "pinstat_update":
                return TestResult(name, False, "missing monitor update after OFF")

            return TestResult(name, True, f"monitor received updates for pin {pin}")

        finally:
            await mon_ws.close()
            await ctl_ws.close()

    except Exception as exc:
        return TestResult(name, False, str(exc))


async def test_alloff(control_uri: str) -> TestResult:
    """Verify ALLOFF works on /control."""
    name = "alloff"

    try:
        ws, _ = await open_ws(control_uri)

        try:
            await send_json(ws, {"cmd": "ALLOFF"})
            resp = await recv_json(ws)

            if resp.get("ok") != 1 or resp.get("cmd") != "ALLOFF":
                return TestResult(name, False, "ALLOFF failed")

            return TestResult(name, True, "ALLOFF OK")

        finally:
            await ws.close()

    except Exception as exc:
        return TestResult(name, False, str(exc))


async def run_default_suite(
    control_uri: str,
    monitor_uri: str,
    pin: int,
) -> List[TestResult]:
    """Run the full default test suite."""
    results = []

    results.append(await test_monitor_basic(monitor_uri))
    results.append(await test_monitor_reject_control(monitor_uri))
    results.append(await test_control_basic(control_uri))
    results.append(await test_control_reject_gateway(control_uri))
    results.append(await test_event_flow(control_uri, monitor_uri, pin))
    results.append(await test_alloff(control_uri))

    return results


async def run_monitor_suite(monitor_uri: str) -> List[TestResult]:
    """Run tests that require only the public monitor port."""
    return [
        await test_monitor_basic(monitor_uri),
        await test_monitor_reject_control(monitor_uri),
    ]


async def test_control_denied(control_uri: str) -> TestResult:
    """Verify that this client's IP is denied by the control port."""
    name = "control-ip-denied"

    try:
        ws = await websockets.connect(control_uri)

        try:
            resp = await recv_json(ws)
            if (
                resp.get("ok") == 0
                and resp.get("error") == "control access denied"
            ):
                return TestResult(name, True, "control IP restriction active")

            return TestResult(
                name,
                False,
                f"unexpected first response: {summarize(resp)}",
            )
        finally:
            await ws.close()

    except Exception as exc:
        return TestResult(name, False, str(exc))


def print_result(result: TestResult) -> None:
    """Print one PASS/FAIL line."""
    if result.passed:
        print(f"PASS  {result.name}: {result.detail}")
    else:
        print(f"FAIL  {result.name}: {result.detail}")


def print_summary(results: List[TestResult]) -> int:
    """Print final summary and return exit code."""
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    print("\n=== TEST SUMMARY ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        print("Failed tests:")
        for result in results:
            if not result.passed:
                print(f"  - {result.name}: {result.detail}")
        return 1

    print("All tests passed.")
    return 0


async def follow_monitor(monitor_uri: str) -> int:
    """Subscribe and print monitor events forever."""
    try:
        ws, hello = await open_ws(monitor_uri)

        if hello.get("event") != "connected":
            print("FAIL  follow: missing connected hello")
            await ws.close()
            return 1

        await send_json(ws, {"gateway": "subscribe"})
        snapshot = await recv_json(ws)
        subscribed = await recv_json(ws)

        if snapshot.get("event") != "pinstat_snapshot":
            print("FAIL  follow: missing snapshot")
            await ws.close()
            return 1

        if subscribed.get("event") != "subscribed":
            print("FAIL  follow: missing subscribed ack")
            await ws.close()
            return 1

        print("PASS  follow: subscribed successfully")
        print("Waiting for monitor events. Press Ctrl+C to stop.")

        try:
            while True:
                await recv_json(ws, timeout=None)
        finally:
            await ws.close()

        return 0

    except Exception as exc:
        print(f"FAIL  follow: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(
        description="Test split WebSocket gateway protocol"
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="gateway host used to build default WebSocket URIs",
    )

    parser.add_argument(
        "--control-port",
        type=int,
        default=8765,
        help="control WebSocket port (default: 8765)",
    )

    parser.add_argument(
        "--monitor-port",
        type=int,
        default=8766,
        help="monitor WebSocket port (default: 8766)",
    )

    parser.add_argument(
        "--control-uri",
        help="complete control WebSocket URI; overrides --host/--control-port",
    )

    parser.add_argument(
        "--monitor-uri",
        help="complete monitor WebSocket URI; overrides --host/--monitor-port",
    )

    parser.add_argument(
        "--pin",
        type=int,
        default=0,
        help="linear pin index used by event-flow test",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print full JSON I/O",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--follow",
        action="store_true",
        help="follow monitor events instead of running the default full test suite",
    )

    mode.add_argument(
        "--monitor-only",
        action="store_true",
        help="run only tests for the publicly accessible monitor port",
    )
    mode.add_argument(
        "--expect-control-denied",
        action="store_true",
        help="verify that this client's IP is rejected by the control port",
    )

    return parser


def websocket_host(host: str) -> str:
    """Wrap a bare IPv6 address for use in a WebSocket URI."""
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


async def async_main() -> int:
    """Async entry point."""
    global VERBOSE

    parser = build_parser()
    args = parser.parse_args()
    VERBOSE = args.verbose

    host = websocket_host(args.host)
    control_uri = args.control_uri or f"ws://{host}:{args.control_port}"
    monitor_uri = args.monitor_uri or f"ws://{host}:{args.monitor_port}"

    if args.follow:
        return await follow_monitor(monitor_uri)

    if args.expect_control_denied:
        result = await test_control_denied(control_uri)
        print_result(result)
        return print_summary([result])

    if args.monitor_only:
        print("Running monitor-only WebSocket tests...\n")
        results = await run_monitor_suite(monitor_uri)
    else:
        print("Running full WebSocket protocol test suite...")
        print(f"  control: {control_uri}")
        print(f"  monitor: {monitor_uri}\n")
        results = await run_default_suite(control_uri, monitor_uri, args.pin)

    print()
    for result in results:
        print_result(result)

    return print_summary(results)


def main() -> int:
    """Sync wrapper for async main."""
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"FAIL  fatal: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
