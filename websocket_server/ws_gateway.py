#!/usr/bin/env python3

"""
WebSocket <-> UART gateway for Pico switching matrix controller.

Features
--------
- Persistent UART connection
- One UART command at a time
- Ignore non-JSON UART noise
- Cache latest PINSTAT ALL result
- Separate monitor/control websocket endpoints
- Broadcast state updates to monitor subscribers only
- Graceful handling of normal websocket disconnects
- Compact operational logging
"""

import asyncio
import ipaddress
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Set

import serial
import websockets
from websockets.exceptions import ConnectionClosed


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

UART_PORT = "/dev/serial0"
UART_BAUDRATE = 115200

UART_READ_TIMEOUT = 0.1
UART_WRITE_TIMEOUT = 1.0
UART_COMMAND_TIMEOUT = 3.0

UART_STARTUP_SETTLE = 0.02
UART_DRAIN_DURATION = 0.01

WS_HOST = "0.0.0.0"
WS_CONTROL_PORT = 8765
WS_MONITOR_PORT = 8766

# Comma-separated IPv4/IPv6 addresses or CIDR networks allowed to use
# /control. When unset, only clients on this Raspberry Pi are allowed.
# Example:
#   CONTROL_ALLOWED_NETWORKS="192.168.0.50/32,192.168.0.64/26"
CONTROL_ALLOWED_NETWORKS = tuple(
    ipaddress.ip_network(item.strip(), strict=False)
    for item in os.environ.get(
        "CONTROL_ALLOWED_NETWORKS",
        "127.0.0.1/32",
    ).split(",")
    if item.strip()
)

LOG_LEVEL = logging.INFO


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("ws_gateway")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def json_error(msg: str, **extra: Any) -> Dict[str, Any]:
    """Build a gateway-side JSON error response."""
    obj: Dict[str, Any] = {
        "ok": 0,
        "error": msg,
        "source": "gateway",
    }
    obj.update(extra)
    return obj


def build_pin_map() -> Dict[str, int]:
    """Build matrix label -> linear pin mapping."""
    mapping: Dict[str, int] = {}

    for row in range(16):
        row_letter = chr(ord("A") + row)
        for col in range(16):
            label = f"{row_letter}{col:02d}"
            mapping[label] = row * 16 + col

    return mapping


def peer_name(websocket: Any) -> str:
    """Return readable websocket peer name."""
    try:
        return str(websocket.remote_address)
    except Exception:
        return "<unknown>"


def websocket_client_ip(websocket: Any) -> Optional[Any]:
    """Return the normalized WebSocket client IP address, if available."""
    try:
        remote = websocket.remote_address
        if not isinstance(remote, tuple) or not remote:
            return None

        address_text = str(remote[0]).split("%", 1)[0]
        address = ipaddress.ip_address(address_text)

        # Normalize IPv4-mapped IPv6 addresses such as ::ffff:192.168.0.50.
        if isinstance(address, ipaddress.IPv6Address):
            if address.ipv4_mapped is not None:
                return address.ipv4_mapped

        return address
    except (AttributeError, TypeError, ValueError):
        return None


def control_ip_allowed(websocket: Any) -> bool:
    """Return whether this WebSocket peer may access /control."""
    address = websocket_client_ip(websocket)
    if address is None:
        return False

    return any(
        address.version == network.version and address in network
        for network in CONTROL_ALLOWED_NETWORKS
    )


async def safe_send_json(websocket: Any, payload: Dict[str, Any]) -> bool:
    """
    Send one JSON object safely.

    Returns:
        True  -> send succeeded
        False -> websocket already closed
    """
    try:
        await websocket.send(json.dumps(payload))
        return True
    except ConnectionClosed:
        return False


# ---------------------------------------------------------------------
# UART Pico client
# ---------------------------------------------------------------------

class PicoUART:
    """Persistent UART client for Pico JSON command firmware."""

    def __init__(self) -> None:
        self.ser: Optional[serial.Serial] = None
        self.lock = threading.Lock()

    def open(self) -> None:
        """Open UART if not already open."""
        if self.ser and self.ser.is_open:
            return

        log.info("Opening UART %s @ %d", UART_PORT, UART_BAUDRATE)

        self.ser = serial.Serial(
            UART_PORT,
            UART_BAUDRATE,
            timeout=UART_READ_TIMEOUT,
            write_timeout=UART_WRITE_TIMEOUT,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

        time.sleep(UART_STARTUP_SETTLE)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.drain()

        log.info("UART opened")

    def close(self) -> None:
        """Close UART if open."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            log.info("UART closed")
        self.ser = None

    def reopen(self) -> None:
        """Close and reopen UART."""
        log.warning("Reopening UART")
        self.close()
        self.open()

    def drain(self) -> None:
        """Drain pending UART input for a short time."""
        deadline = time.monotonic() + UART_DRAIN_DURATION

        while time.monotonic() < deadline:
            line = self.ser.readline()
            if not line:
                continue

    def read_json(self) -> Dict[str, Any]:
        """
        Read one JSON object response from UART.

        Non-JSON lines are ignored to tolerate noise or startup text.
        """
        deadline = time.monotonic() + UART_COMMAND_TIMEOUT
        last_line = None

        while time.monotonic() < deadline:
            raw = self.ser.readline()

            if not raw:
                continue

            line = raw.decode("utf-8", errors="replace").strip()

            if not line:
                continue

            last_line = line

            try:
                obj = json.loads(line)
            except Exception:
                continue

            if isinstance(obj, dict):
                return obj

        raise RuntimeError(f"UART timeout (last_line={last_line!r})")

    def send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send one JSON command to Pico and return one JSON response.

        UART access is serialized with a thread lock.
        """
        with self.lock:
            if not self.ser or not self.ser.is_open:
                self.open()

            msg = json.dumps(payload, separators=(",", ":")) + "\n"

            try:
                self.ser.write(msg.encode("utf-8"))
                self.ser.flush()
            except Exception:
                self.reopen()
                raise

            return self.read_json()


# ---------------------------------------------------------------------
# Gateway server
# ---------------------------------------------------------------------

class Gateway:
    """Async WebSocket gateway around the persistent Pico UART client."""

    def __init__(self, pico: PicoUART) -> None:
        self.pico = pico
        self.lock = asyncio.Lock()
        self.last_pinstat_all: Optional[Dict[str, Any]] = None
        self.monitor_subscribers: Set[Any] = set()

    def websocket_path(self, websocket: Any, path_hint: Optional[str] = None) -> str:
        """
        Return normalized websocket request path.

        Compatible with multiple websockets versions.
        """
        if isinstance(path_hint, str) and path_hint:
            return path_hint.split("?", 1)[0]

        path = getattr(websocket, "path", None)
        if isinstance(path, str):
            return path.split("?", 1)[0]

        request = getattr(websocket, "request", None)
        if request is not None:
            req_path = getattr(request, "path", None)
            if isinstance(req_path, str):
                return req_path.split("?", 1)[0]

        return "/"

    async def pico_send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Serialize Pico access with one async lock.

        Cache is invalidated before state-changing commands and updated
        automatically when PINSTAT ALL succeeds.
        """
        async with self.lock:
            cmd = payload.get("cmd", "<none>")
            log.info("Pico command: %s", cmd)

            if isinstance(cmd, str) and cmd.upper() in ("ON", "OFF", "ALLOFF"):
                # The hardware may change even if the response is lost or a
                # multi-pin command fails partway through. Never serve a
                # snapshot taken before this command as the current state.
                self.last_pinstat_all = None

            resp = await asyncio.to_thread(self.pico.send, payload)

            if (
                isinstance(resp, dict)
                and resp.get("ok") == 1
                and resp.get("cmd") == "PINSTAT"
                and resp.get("which") == "ALL"
                and isinstance(resp.get("pins"), list)
            ):
                self.last_pinstat_all = resp

            return resp

    async def refresh_pinstat_all(self) -> Dict[str, Any]:
        """Query PINSTAT ALL from Pico and update cache."""
        resp = await self.pico_send({
            "cmd": "PINSTAT",
            "which": "ALL",
        })

        if resp.get("ok") != 1:
            raise RuntimeError(f"failed to refresh PINSTAT ALL: {resp}")

        return resp

    async def gateway_get(self) -> Dict[str, Any]:
        """Return cached PINSTAT ALL if available; otherwise fetch it once."""
        if self.last_pinstat_all is not None:
            return {
                "ok": 1,
                "event": "get",
                "source": "gateway",
                "cached": 1,
                "data": self.last_pinstat_all,
            }

        resp = await self.refresh_pinstat_all()

        return {
            "ok": 1,
            "event": "get",
            "source": "gateway",
            "cached": 0,
            "data": resp,
        }

    async def send_snapshot(self, websocket: Any, *, cached_flag: int) -> bool:
        """Send one state snapshot to a websocket."""
        if self.last_pinstat_all is None:
            await self.refresh_pinstat_all()

        return await safe_send_json(websocket, {
            "ok": 1,
            "event": "pinstat_snapshot",
            "source": "gateway",
            "cached": cached_flag,
            "data": self.last_pinstat_all,
        })

    async def broadcast_state_update(self) -> None:
        """Broadcast latest state snapshot to monitor subscribers only."""
        if not self.monitor_subscribers:
            return

        try:
            await self.refresh_pinstat_all()
        except Exception as exc:
            log.warning("Broadcast refresh failed: %s", exc)
            return

        payload = {
            "ok": 1,
            "event": "pinstat_update",
            "source": "gateway",
            "data": self.last_pinstat_all,
        }

        dead = []

        for ws in list(self.monitor_subscribers):
            ok = await safe_send_json(ws, payload)
            if not ok:
                dead.append(ws)

        for ws in dead:
            self.monitor_subscribers.discard(ws)

        log.info(
            "Broadcasted pinstat_update to %d monitor subscribers",
            len(self.monitor_subscribers),
        )

    async def subscribe_monitor(self, websocket: Any) -> Dict[str, Any]:
        """Register websocket as monitor subscriber and send current snapshot."""
        self.monitor_subscribers.add(websocket)
        log.info(
            "Monitor subscriber added: %s (total=%d)",
            peer_name(websocket),
            len(self.monitor_subscribers),
        )

        try:
            ok = await self.send_snapshot(
                websocket,
                cached_flag=1 if self.last_pinstat_all else 0,
            )
        except Exception as exc:
            self.monitor_subscribers.discard(websocket)
            return json_error(str(exc))

        if not ok:
            self.monitor_subscribers.discard(websocket)
            return json_error("websocket closed during subscribe")

        return {
            "ok": 1,
            "event": "subscribed",
            "source": "gateway",
            "channel": "monitor",
        }

    async def unsubscribe_monitor(self, websocket: Any) -> Dict[str, Any]:
        """Remove websocket from monitor subscriber set."""
        self.monitor_subscribers.discard(websocket)
        log.info(
            "Monitor subscriber removed: %s (total=%d)",
            peer_name(websocket),
            len(self.monitor_subscribers),
        )

        return {
            "ok": 1,
            "event": "unsubscribed",
            "source": "gateway",
            "channel": "monitor",
        }

    async def handle_monitor(self, websocket: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle monitor-only commands."""
        gateway_cmd = payload.get("gateway")

        if gateway_cmd == "ping":
            return {
                "ok": 1,
                "event": "gateway_pong",
                "source": "gateway",
                "channel": "monitor",
            }

        if gateway_cmd == "get":
            return await self.gateway_get()

        if gateway_cmd == "map":
            return {
                "ok": 1,
                "event": "map",
                "source": "gateway",
                "map": build_pin_map(),
            }

        if gateway_cmd == "subscribe":
            return await self.subscribe_monitor(websocket)

        if gateway_cmd == "unsubscribe":
            return await self.unsubscribe_monitor(websocket)

        return json_error(
            "monitor endpoint accepts only gateway commands",
            path="/monitor",
        )

    async def handle_control(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle control-only commands."""
        if "gateway" in payload:
            return json_error(
                "control endpoint does not accept gateway commands",
                path="/control",
            )

        try:
            resp = await self.pico_send(payload)
        except Exception as exc:
            log.warning("Control command failure: %s", exc)
            return json_error(str(exc))

        if (
            isinstance(resp, dict)
            and resp.get("ok") == 1
            and resp.get("cmd") in ("ON", "OFF", "ALLOFF")
        ):
            await self.broadcast_state_update()

        return resp

    async def handle(self, websocket, path: Optional[str] = None) -> None:
        """Handle one WebSocket client connection."""
        norm_path = self.websocket_path(websocket, path)
        name = peer_name(websocket)

        log.info("Client connected: %s path=%s", name, norm_path)

        if norm_path == "/control" and not control_ip_allowed(websocket):
            client_ip = websocket_client_ip(websocket)
            log.warning(
                "Control access denied: ip=%s peer=%s",
                client_ip if client_ip is not None else "<unknown>",
                name,
            )

            await safe_send_json(websocket, json_error(
                "control access denied",
                path="/control",
            ))
            await websocket.close(code=1008, reason="control access denied")
            return

        try:
            ok = await safe_send_json(websocket, {
                "ok": 1,
                "event": "connected",
                "source": "gateway",
                "path": norm_path,
            })
            if not ok:
                return

            async for message in websocket:
                try:
                    payload = json.loads(message)
                except Exception:
                    ok = await safe_send_json(websocket, json_error("invalid JSON"))
                    if not ok:
                        return
                    continue

                if not isinstance(payload, dict):
                    ok = await safe_send_json(websocket, json_error("JSON must be object"))
                    if not ok:
                        return
                    continue

                if "gateway" in payload:
                    log.info(
                        "Gateway command from %s on %s: %s",
                        name,
                        norm_path,
                        payload.get("gateway"),
                    )
                elif "cmd" in payload:
                    log.info(
                        "Pico command from %s on %s: %s",
                        name,
                        norm_path,
                        payload.get("cmd"),
                    )

                if norm_path == "/monitor":
                    resp = await self.handle_monitor(websocket, payload)
                elif norm_path == "/control":
                    resp = await self.handle_control(payload)
                else:
                    resp = json_error("unknown websocket path", path=norm_path)

                ok = await safe_send_json(websocket, resp)
                if not ok:
                    return

        except ConnectionClosed:
            log.info("Client disconnected: %s path=%s", name, norm_path)
        finally:
            self.monitor_subscribers.discard(websocket)
            log.info("Connection cleanup done: %s path=%s", name, norm_path)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

async def main() -> None:
    pico = PicoUART()
    pico.open()

    gateway = Gateway(pico)

    async def control_handler(websocket: Any, path: Optional[str] = None) -> None:
        # Port 8765 is always control, regardless of the requested URL path.
        await gateway.handle(websocket, "/control")

    async def monitor_handler(websocket: Any, path: Optional[str] = None) -> None:
        # Port 8766 is always monitor, regardless of the requested URL path.
        await gateway.handle(websocket, "/monitor")

    async with (
        websockets.serve(control_handler, WS_HOST, WS_CONTROL_PORT),
        websockets.serve(monitor_handler, WS_HOST, WS_MONITOR_PORT)
    ):
        log.info("Control WebSocket running on ws://%s:%d", WS_HOST, WS_CONTROL_PORT)
        log.info("Monitor WebSocket running on ws://%s:%d", WS_HOST, WS_MONITOR_PORT)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
