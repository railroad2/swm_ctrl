#!/usr/bin/env python3

import argparse
import json
import sys
from typing import List

from pico_uart_client import PicoClientError, PicoUARTClient


def colorize(text: str, enabled: bool, present: int) -> str:
    if not enabled:
        return text
    return f"\033[32m{text}\033[0m" if present else f"\033[31m{text}\033[0m"


def print_frame_line(width: int) -> None:
    print("+" + "-" * width + "+")


def print_pcf_all(present: List[int], frame: bool, color: bool) -> None:
    if len(present) != 16:
        raise ValueError("ALL mode requires 16 entries")
    body = " ".join(colorize(f"{i:02d}:{value}", color, value) for i, value in enumerate(present))
    if frame:
        print_frame_line(len(body))
        print("|" + body + "|")
        print_frame_line(len(body))
    else:
        print(body)


def print_pcf_one(pcf_id: int, present: int, frame: bool, color: bool) -> None:
    body = colorize(f"{pcf_id:02d}:{present}", color, present)
    if frame:
        print_frame_line(len(body))
        print("|" + body + "|")
        print_frame_line(len(body))
    else:
        print(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read PCFSTAT from Pico over UART.")
    parser.add_argument("item", nargs="?", default="ALL", help="ALL or PCF id")
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--noframe", action="store_true")
    parser.add_argument("--nocolor", action="store_true")
    parser.add_argument("-v", action="store_true", help="Verbose mode.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.item.upper() == "ALL":
        which = "ALL"
    else:
        try:
            which = int(args.item)
        except ValueError:
            print("error: item must be ALL or integer pcf id")
            return 1
        if not 0 <= which <= 15:
            print("error: pcf id out of range (0..15)")
            return 1

    try:
        with PicoUARTClient(port=args.port, baudrate=args.baudrate, command_timeout=3.0, debug=args.v) as client:
            response = client.pcfstat(which)
        if args.v:
            print("RX:", json.dumps(response))
        present = response["present"]
        if which == "ALL":
            print_pcf_all(present, not args.noframe, not args.nocolor)
        else:
            print_pcf_one(which, present, not args.noframe, not args.nocolor)
        return 0
    except (PicoClientError, ValueError, KeyError) as exc:
        print("error:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
