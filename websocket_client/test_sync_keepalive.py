import unittest

from swm_ctrl.websocket_client.websocket_client import WebSocketClient
from swm_ctrl.websocket_client.websocket_client_sync import WebSocketClientSync


class SyncKeepaliveTests(unittest.TestCase):
    def test_async_client_keeps_websocket_default_heartbeat(self):
        client = WebSocketClient("ws://localhost:8765")

        self.assertEqual(client.ping_interval, 20.0)

    def test_sync_client_disables_automatic_heartbeat(self):
        client = WebSocketClientSync("ws://localhost:8765")

        async_client = client._ensure_client()

        self.assertIsNone(client.ping_interval)
        self.assertIsNone(async_client.ping_interval)
        client.close()

    def test_sync_heartbeat_can_be_enabled_explicitly(self):
        client = WebSocketClientSync(
            "ws://localhost:8765",
            ping_interval=30.0,
        )

        async_client = client._ensure_client()

        self.assertEqual(async_client.ping_interval, 30.0)
        client.close()


if __name__ == "__main__":
    unittest.main()
