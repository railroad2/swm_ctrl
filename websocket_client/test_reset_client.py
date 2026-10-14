import argparse
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

from swm_ctrl.websocket_client import sw_control
from swm_ctrl.websocket_client.websocket_client import WebSocketClient
from swm_ctrl.websocket_client.websocket_client_sync import WebSocketClientSync


class AsyncResetClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_gateway_reset_with_extended_timeout(self):
        response = {
            "ok": 1,
            "event": "reset",
            "reset_executed": 1,
            "restarted": 1,
        }
        client = WebSocketClient("ws://localhost:8765/control")
        client._send_and_recv = AsyncMock(return_value=response)

        result = await client.reset()

        self.assertIs(result, response)
        client._send_and_recv.assert_awaited_once_with(
            {"gateway": "reset"},
            timeout=15.0,
        )

    async def test_rejects_unverified_reset_response(self):
        client = WebSocketClient("ws://localhost:8765/control")
        client._send_and_recv = AsyncMock(return_value={
            "ok": 0,
            "event": "reset",
            "reset_executed": 1,
            "restarted": 0,
        })

        with self.assertRaisesRegex(Exception, "reset response"):
            await client.reset()


class SyncResetClientTests(unittest.TestCase):
    def test_forwards_reset_timeout(self):
        client = WebSocketClientSync("ws://localhost:8765/control")
        async_client = MagicMock()
        async_client.reset.return_value = "reset-coroutine"
        client._client = async_client
        client._connected = True
        client._run = MagicMock(return_value={"ok": 1})

        result = client.reset(timeout=20.0)

        self.assertEqual(result, {"ok": 1})
        async_client.reset.assert_called_once_with(timeout=20.0)
        client._run.assert_called_once_with("reset-coroutine")


class ResetCommandTests(unittest.TestCase):
    def test_parser_registers_reset_command(self):
        args = sw_control.build_parser().parse_args(["reset"])

        self.assertIs(args.func, sw_control.cmd_reset)
        self.assertEqual(args.wait_timeout, 15.0)

    def test_reset_command_uses_control_endpoint(self):
        args = argparse.Namespace(
            uri="ws://swm:8765",
            control_uri=None,
            timeout=5.0,
            wait_timeout=18.0,
        )
        client = MagicMock()
        context = MagicMock()
        context.__enter__.return_value = client
        context.__exit__.return_value = False

        with patch.object(
            sw_control,
            "WebSocketClientSync",
            return_value=context,
        ) as client_class, redirect_stdout(StringIO()) as output:
            result = sw_control.cmd_reset(args)

        self.assertEqual(result, 0)
        client_class.assert_called_once_with(
            "ws://swm:8765/control",
            timeout=5.0,
        )
        client.reset.assert_called_once_with(timeout=18.0)
        self.assertEqual(output.getvalue().strip(), "RESET SUCCESS")


if __name__ == "__main__":
    unittest.main()
