"""WebSocket clients for the switching-matrix gateway."""

from .websocket_client import (
    PinInput,
    WebSocketClient,
    WebSocketClientError,
    WebSocketProtocolError,
    WebSocketTransportError,
    parse_matrix_label,
    parse_pin_tokens,
    pin_to_label,
    row_col_to_pin,
)
from .websocket_client_sync import WebSocketClientSync

__all__ = [
    "PinInput",
    "WebSocketClient",
    "WebSocketClientError",
    "WebSocketClientSync",
    "WebSocketProtocolError",
    "WebSocketTransportError",
    "parse_matrix_label",
    "parse_pin_tokens",
    "pin_to_label",
    "row_col_to_pin",
]
