#!/usr/bin/env python3

import sys

from pico_uart_client import PicoClientError, PicoUARTClient


def main():

    if len(sys.argv) < 2:
        print("usage: on.py <pin> [pin...]")
        return 1

    try:
        pins = [int(x) for x in sys.argv[1:]]
    except ValueError:
        print("error: pins must be integers")
        return 1

    for p in pins:
        if p < 0 or p > 255:
            print(f"error: pin out of range: {p}")
            return 1

    try:
        with PicoUARTClient(command_timeout=2.0, debug=True) as client:
            resp = client.on(pins)
            print("RX:", resp)
        print("SUCCESS")
        return 0
    except PicoClientError as exc:
        print("error:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
