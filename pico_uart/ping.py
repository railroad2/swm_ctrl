#!/usr/bin/env python3

import sys

from pico_uart_client import PicoClientError, PicoUARTClient


def main() -> int:
    """Send one PING command to Pico and verify the JSON response."""
    try:
        with PicoUARTClient(command_timeout=2.0, debug=True) as client:
            ok, response = client.ping()
            if not ok or response is None:
                print("FAIL: PING failed")
                return 1

            print(f"RX: {response}")
            print("PASS: PING succeeded")
            return 0
    except PicoClientError as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
