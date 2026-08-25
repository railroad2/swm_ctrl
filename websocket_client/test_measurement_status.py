import unittest
from unittest.mock import AsyncMock

from swm_ctrl.websocket_client.websocket_client import WebSocketClient


class MeasurementStatusClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_publishes_only_target_level_progress(self):
        client = WebSocketClient("ws://localhost:8765")
        client._send_and_recv = AsyncMock(return_value={
            "ok": 1,
            "event": "measurement_status",
        })

        await client.publish_measurement_status(
            status="running",
            kind="IV",
            mode="channel",
            target=18,
            completed=2,
            total=10,
        )

        payload = client._send_and_recv.await_args.args[0]
        self.assertEqual(payload["gateway"], "measurement")
        self.assertEqual(payload["target"], 18)
        self.assertEqual(payload["completed"], 2)
        self.assertEqual(payload["total"], 10)
        self.assertNotIn("voltage", payload)
        self.assertNotIn("sweep", payload)


if __name__ == "__main__":
    unittest.main()
