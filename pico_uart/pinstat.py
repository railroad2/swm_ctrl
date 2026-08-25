#!/usr/bin/env python3

import argparse
import json
import sys
from typing import List, Optional

from pico_uart_client import PicoClientError, PicoUARTClient


def colorize(text: str, enabled: bool, state: int, highlight: bool) -> str:
    if not enabled:
        return text
    if highlight:
        return f"\033[1;42;30m{text}\033[0m" if state else f"\033[1;41;37m{text}\033[0m"
    return f"\033[32m{text}\033[0m" if state else f"\033[90m{text}\033[0m"


def print_frame_line(width: int) -> None:
    print("+" + "-" * width + "+")


def print_pins_all(pins: List[int], highlights: Optional[List[int]], frame: bool, color: bool) -> None:
    if len(pins) != 256:
        raise ValueError("ALL mode requires 256 pins")
    width = 4 + 16 * 2 - 1
    if frame:
        print_frame_line(width)
    for row in range(16):
        base = row * 16
        cells = []
        for col in range(16):
            channel = base + col
            state = pins[channel]
            highlighted = highlights is not None and channel in highlights
            cells.append(colorize(str(state), color, state, highlighted))
        line = f"{base:03d}: " + " ".join(cells)
        print(f"|{line}|" if frame else line)
    if frame:
        print_frame_line(width)


def print_pins_pcf(pcf_id: int, pins: List[int], highlights: Optional[List[int]], frame: bool, color: bool) -> None:
    if len(pins) != 16:
        raise ValueError("PCF mode requires 16 pins")
    entries = []
    for offset, state in enumerate(pins):
        channel = pcf_id * 16 + offset
        highlighted = highlights is not None and channel in highlights
        entries.append(colorize(f"{channel:03d}:{state}", color, state, highlighted))
    body = " ".join(entries)
    if frame:
        print_frame_line(len(body))
        print("|" + body + "|")
        print_frame_line(len(body))
    else:
        print(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read PINSTAT from Pico over UART.")
    parser.add_argument("items", nargs="*", help="ALL, one PCF id, or channel numbers")
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--noframe", action="store_true")
    parser.add_argument("--nocolor", action="store_true")
    parser.add_argument("-v", action="store_true", help="Verbose mode.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mode = "ALL"
    which = "ALL"
    highlights: Optional[List[int]] = None

    if len(args.items) == 1 and args.items[0].upper() == "ALL":
        pass
    elif len(args.items) == 1:
        try:
            value = int(args.items[0])
        except ValueError:
            print("error: argument must be ALL, one PCF id, or channel numbers")
            return 1
        if 0 <= value <= 15:
            mode, which = "PCF", value
        elif 0 <= value <= 255:
            highlights = [value]
        else:
            print("error: value out of range")
            return 1
    elif len(args.items) > 1:
        try:
            highlights = [int(item) for item in args.items]
        except ValueError:
            print("error: all items must be integers or ALL")
            return 1
        if any(channel < 0 or channel > 255 for channel in highlights):
            print("error: channel out of range")
            return 1

    try:
        with PicoUARTClient(port=args.port, baudrate=args.baudrate, command_timeout=3.0, debug=args.v) as client:
            response = client.pinstat(which)
        if args.v:
            print("RX:", json.dumps(response))
        if mode == "ALL":
            print_pins_all(response["pins"], highlights, not args.noframe, not args.nocolor)
        else:
            print_pins_pcf(int(which), response["pins"], highlights, not args.noframe, not args.nocolor)
        return 0
    except (PicoClientError, ValueError, KeyError) as exc:
        print("error:", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
