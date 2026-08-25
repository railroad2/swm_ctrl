import unittest
from unittest.mock import AsyncMock

from websocket_client import WebSocketClient


class WebSocketClientPinInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_on_accepts_one_list(self):
        client = WebSocketClient("ws://test")
        response = {"ok": 1, "cmd": "ON", "results": []}
        client._send_pico_command = AsyncMock(return_value=response)

        result = await client.on([3, 1, 2])

        client._send_pico_command.assert_awaited_once_with(
            {"cmd": "ON", "pins": [1, 2, 3]},
            "ON",
        )
        self.assertIs(result, response)

    async def test_existing_variadic_input_still_works(self):
        client = WebSocketClient("ws://test")
        response = {"ok": 1, "cmd": "OFF", "results": []}
        client._send_pico_command = AsyncMock(return_value=response)

        result = await client.off(3, 1, 2)

        client._send_pico_command.assert_awaited_once_with(
            {"cmd": "OFF", "pins": [1, 2, 3]},
            "OFF",
        )
        self.assertIs(result, response)

    async def test_off_accepts_list_containing_all(self):
        client = WebSocketClient("ws://test")
        response = {"ok": 1, "cmd": "ALLOFF"}
        client.alloff = AsyncMock(return_value=response)

        result = await client.off(["all"])

        client.alloff.assert_awaited_once_with()
        self.assertIs(result, response)


if __name__ == "__main__":
    unittest.main()
