import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from swm_ctrl.pico_uart import PicoTimeoutError, UART_REQUEST_ID_FIELD
from swm_ctrl.websocket_server.ws_gateway import (
    Gateway,
    WS_CONTROL_PING_INTERVAL,
    parse_measurement_status,
    run_mpremote_reset,
)


class FakePico:
    pass


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(json.loads(message))


class FakeProcess:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.killed = False

    async def communicate(self):
        return self.stdout, self.stderr

    def kill(self):
        self.killed = True
        self.returncode = -9


class ResetPico:
    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.reopen_count = 0

    def send_command(self, payload, **options):
        self.calls.append((payload, options))
        if self.error is not None:
            raise self.error
        if payload["cmd"] == "PING":
            return {
                "ok": 1,
                "cmd": "PING",
                "pong": 1,
                UART_REQUEST_ID_FIELD: 10,
            }
        if payload["cmd"] == "PINSTAT":
            return {
                "ok": 1,
                "cmd": "PINSTAT",
                "which": "ALL",
                "pins": [0] * 256,
                UART_REQUEST_ID_FIELD: 11,
            }
        raise AssertionError(f"unexpected payload: {payload}")

    def reopen(self):
        self.reopen_count += 1


class MpremoteResetTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_fixed_command_without_shell(self):
        process = FakeProcess(stdout=b"reset complete\n")
        creator = AsyncMock(return_value=process)

        with patch("asyncio.create_subprocess_exec", creator):
            await run_mpremote_reset("/usr/bin/mpremote", timeout=2.0)

        creator.assert_awaited_once_with(
            "/usr/bin/mpremote",
            "reset",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def test_reports_nonzero_exit(self):
        process = FakeProcess(returncode=2, stderr=b"reset failed")

        with patch(
            "asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ):
            with self.assertRaisesRegex(RuntimeError, "exit code 2"):
                await run_mpremote_reset("mpremote", timeout=2.0)


class ResetGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_reset_runs_mpremote_and_verifies_pico(self):
        pico = ResetPico()
        gateway = Gateway(pico)
        gateway.last_pinstat_all = {"pins": [1] * 256}

        with patch(
            "swm_ctrl.websocket_server.ws_gateway.run_mpremote_reset",
            AsyncMock(),
        ) as reset_command, patch(
            "swm_ctrl.websocket_server.ws_gateway.RESET_BOOT_DELAY",
            0,
        ):
            response = await gateway.handle_control({"gateway": "reset"})

        self.assertEqual(
            response,
            {
                "ok": 1,
                "event": "reset",
                "source": "gateway",
                "reset_executed": 1,
                "restarted": 1,
            },
        )
        reset_command.assert_awaited_once_with()
        self.assertEqual(
            [payload for payload, _ in pico.calls],
            [{"cmd": "PING"}, {"cmd": "PINSTAT", "which": "ALL"}],
        )
        self.assertEqual(gateway.last_pinstat_all["pins"], [0] * 256)
        self.assertNotIn(
            UART_REQUEST_ID_FIELD,
            gateway.last_pinstat_all,
        )

    async def test_reset_command_failure_is_not_reported_as_executed(self):
        gateway = Gateway(ResetPico())

        with patch(
            "swm_ctrl.websocket_server.ws_gateway.run_mpremote_reset",
            AsyncMock(side_effect=RuntimeError("mpremote missing")),
        ):
            response = await gateway.handle_control({"gateway": "reset"})

        self.assertEqual(response["ok"], 0)
        self.assertEqual(response["event"], "reset")
        self.assertEqual(response["reset_executed"], 0)
        self.assertEqual(response["restarted"], 0)

    async def test_reset_verification_failure_reports_execution(self):
        pico = ResetPico(error=PicoTimeoutError("no response"))
        gateway = Gateway(pico)

        with patch(
            "swm_ctrl.websocket_server.ws_gateway.run_mpremote_reset",
            AsyncMock(),
        ), patch(
            "swm_ctrl.websocket_server.ws_gateway.RESET_BOOT_DELAY",
            0,
        ), patch(
            "swm_ctrl.websocket_server.ws_gateway.RESET_VERIFY_INTERVAL",
            0,
        ), patch(
            "swm_ctrl.websocket_server.ws_gateway.RESET_VERIFY_ATTEMPTS",
            2,
        ):
            response = await gateway.handle_control({"gateway": "reset"})

        self.assertEqual(response["ok"], 0)
        self.assertEqual(response["event"], "reset")
        self.assertEqual(response["reset_executed"], 1)
        self.assertEqual(response["restarted"], 0)
        self.assertEqual(len(pico.calls), 2)


class MeasurementStatusValidationTests(unittest.TestCase):
    def test_control_server_keepalive_is_disabled_for_blocking_sweeps(self):
        self.assertIsNone(WS_CONTROL_PING_INTERVAL)

    def test_accepts_target_progress_without_sweep_fields(self):
        status = parse_measurement_status({
            "status": "running",
            "kind": "IV",
            "mode": "channel",
            "target": 18,
            "completed": 2,
            "total": 10,
            "voltage": -20,
        })

        self.assertEqual(
            status,
            {
                "status": "running",
                "kind": "IV",
                "mode": "channel",
                "target": 18,
                "completed": 2,
                "total": 10,
            },
        )
        self.assertNotIn("voltage", status)

    def test_rejects_invalid_target_progress(self):
        with self.assertRaisesRegex(ValueError, "target is out of range"):
            parse_measurement_status({
                "status": "running",
                "kind": "CV",
                "mode": "row",
                "target": 16,
                "completed": 0,
                "total": 1,
            })


class MeasurementStatusGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_control_publication_is_cached_and_broadcast(self):
        gateway = Gateway(FakePico())
        monitor = FakeWebSocket()
        gateway.monitor_subscribers.add(monitor)
        payload = {
            "gateway": "measurement",
            "status": "running",
            "kind": "CV",
            "mode": "column",
            "target": 3,
            "completed": 1,
            "total": 4,
        }

        response = await gateway.handle_control(payload)
        if gateway.background_tasks:
            await asyncio.gather(*gateway.background_tasks)

        self.assertEqual(response["event"], "measurement_status")
        self.assertEqual(gateway.measurement_status["target"], 3)
        self.assertEqual(monitor.messages[-1]["event"], "measurement_update")
        self.assertEqual(monitor.messages[-1]["measurement"]["completed"], 1)

        gateway.last_pinstat_all = {
            "ok": 1,
            "cmd": "PINSTAT",
            "which": "ALL",
            "pins": [0] * 256,
        }
        snapshot = await gateway.gateway_get()
        self.assertEqual(snapshot["measurement"], gateway.measurement_status)

    async def test_terminal_status_returns_to_idle_after_delay(self):
        gateway = Gateway(FakePico(), measurement_idle_delay=0.01)
        monitor = FakeWebSocket()
        gateway.monitor_subscribers.add(monitor)

        await gateway.handle_control({
            "gateway": "measurement",
            "status": "stopped",
            "kind": "IV",
            "mode": "channel",
            "target": 7,
            "completed": 2,
            "total": 4,
        })
        await asyncio.sleep(0.02)
        if gateway.background_tasks:
            await asyncio.gather(*gateway.background_tasks)

        self.assertEqual(gateway.measurement_status["status"], "idle")
        self.assertEqual(gateway.measurement_status["completed"], 0)
        self.assertEqual(gateway.measurement_status["total"], 0)
        self.assertEqual(monitor.messages[-1]["event"], "measurement_update")
        self.assertEqual(
            monitor.messages[-1]["measurement"]["status"],
            "idle",
        )

    async def test_new_measurement_cancels_pending_idle_transition(self):
        gateway = Gateway(FakePico(), measurement_idle_delay=0.01)

        await gateway.handle_control({
            "gateway": "measurement",
            "status": "completed",
            "kind": "CV",
            "mode": "row",
            "target": 3,
            "completed": 1,
            "total": 1,
        })
        await gateway.handle_control({
            "gateway": "measurement",
            "status": "starting",
            "kind": "IV",
            "mode": "column",
            "target": None,
            "completed": 0,
            "total": 2,
        })
        await asyncio.sleep(0.02)

        self.assertEqual(gateway.measurement_status["status"], "starting")
        self.assertEqual(gateway.measurement_status["kind"], "IV")


if __name__ == "__main__":
    unittest.main()
