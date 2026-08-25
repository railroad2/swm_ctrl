import asyncio
import json
import unittest

from swm_ctrl.websocket_server.ws_gateway import Gateway, parse_measurement_status


class FakePico:
    pass


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(json.loads(message))


class MeasurementStatusValidationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
