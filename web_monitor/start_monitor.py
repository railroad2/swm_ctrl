#!/usr/bin/env python3
"""Serve the switching-matrix web monitor from its own directory."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
WEB_ROOT = Path(__file__).resolve().parent


def build_parser():
    parser = argparse.ArgumentParser(
        description="Start the switching-matrix web monitor server.",
    )
    parser.add_argument(
        "--host",
        "--bind",
        dest="host",
        default=DEFAULT_HOST,
        help=f"address to bind (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"HTTP port (default: {DEFAULT_PORT})",
    )
    return parser


def main():
    args = build_parser().parse_args()
    if not 0 <= args.port <= 65535:
        raise SystemExit("--port must be between 0 and 65535")

    handler = partial(SimpleHTTPRequestHandler, directory=str(WEB_ROOT))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    host, port = server.server_address[:2]

    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print(f"Web monitor root: {WEB_ROOT}")
    print(f"Web monitor URL:  http://{display_host}:{port}/")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web monitor.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
