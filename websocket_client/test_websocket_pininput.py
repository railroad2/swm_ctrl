"""Unit tests for pin input handled by the neighboring WebSocket client."""

import json
import unittest
from unittest.mock import AsyncMock

from websocket_client import WebSocketClient


class WebSocketClientPinInputTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def print_result(name, pin_input, request, response):
        print(f"\nPASS  {name}")
        print(f"  input:    {pin_input!r}")
        print(f"  request:  {json.dumps(request, sort_keys=True)}")
        print(f"  response: {json.dumps(response, sort_keys=True)}")

    async def test_on_accepts_one_list(self):
        client = WebSocketClient("ws://test")
        response = {"ok": 1, "cmd": "ON", "results": []}
        request = {"cmd": "ON", "pins": [1, 2, 3]}
        client._send_pico_command = AsyncMock(return_value=response)

        result = await client.on([3, 1, 2])

        client._send_pico_command.assert_awaited_once_with(
            request,
            "ON",
        )
        self.assertIs(result, response)
        self.print_result("on accepts one list", [3, 1, 2], request, result)

    async def test_existing_variadic_input_still_works(self):
        client = WebSocketClient("ws://test")
        response = {"ok": 1, "cmd": "OFF", "results": []}
        request = {"cmd": "OFF", "pins": [1, 2, 3]}
        client._send_pico_command = AsyncMock(return_value=response)

        result = await client.off(3, 1, 2)

        client._send_pico_command.assert_awaited_once_with(
            request,
            "OFF",
        )
        self.assertIs(result, response)
        self.print_result("off accepts variadic input", (3, 1, 2), request, result)

    async def test_off_accepts_list_containing_all(self):
        client = WebSocketClient("ws://test")
        response = {"ok": 1, "cmd": "ALLOFF"}
        request = {"cmd": "ALLOFF"}
        client.alloff = AsyncMock(return_value=response)

        result = await client.off(["all"])

        client.alloff.assert_awaited_once_with()
        self.assertIs(result, response)
        self.print_result("off accepts ['all']", ["all"], request, result)


if __name__ == "__main__":
    unittest.main()
