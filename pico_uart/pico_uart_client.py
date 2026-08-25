
import json
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import serial


UART_REQUEST_ID_FIELD = "uart_request_id"
MAX_UART_REQUEST_ID = 2_147_483_647


class PicoClientError(Exception):
    """Base exception for Pico UART client errors."""
    pass


class PicoTimeoutError(PicoClientError):
    """Raised when a command response does not arrive in time."""
    pass


class PicoProtocolError(PicoClientError):
    """Raised when the device returns an invalid or unexpected response."""
    pass


class PicoTransportError(PicoClientError):
    """Raised when the UART transport layer fails."""
    pass


class PicoUARTClient:
    """
    UART JSON client for Pico command processor.

    Design principles:
    - One command at a time
    - One JSON line request -> one JSON line response
    - Ignore non-JSON noise lines
    - Use strict request-response matching by UART request ID
    """

    def __init__(
        self,
        port: str = "/dev/serial0",
        baudrate: int = 115200,
        read_timeout: float = 0.05,
        write_timeout: float = 1.0,
        command_timeout: float = 2.0,
        startup_settle: float = 0.0,
        startup_drain: float = 0.0,
        auto_open: bool = True,
        debug: bool = False,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.command_timeout = command_timeout
        self.startup_settle = startup_settle
        self.startup_drain = startup_drain
        self.debug = debug

        if self.startup_settle < 0:
            raise ValueError("startup_settle must be non-negative")
        if self.startup_drain < 0:
            raise ValueError("startup_drain must be non-negative")

        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._noise_lines: List[str] = []
        self._next_uart_request_id = 1

        if auto_open:
            self.open()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------
    def open(self) -> None:
        """Open the UART port if it is not already open."""
        if self._ser is not None and self._ser.is_open:
            return

        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.read_timeout,
                write_timeout=self.write_timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )

            if self.startup_settle:
                time.sleep(self.startup_settle)

            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()

            if self.startup_drain:
                self._drain_input(duration=self.startup_drain)
        except PicoTransportError:
            self.close()
            raise
        except serial.SerialException as exc:
            self.close()
            raise PicoTransportError(f"Failed to open serial port {self.port}: {exc}") from exc

    def close(self) -> None:
        """Close the UART port."""
        if self._ser is not None:
            try:
                if self._ser.is_open:
                    self._ser.close()
            finally:
                self._ser = None

    def reopen(self) -> None:
        """Close and reopen the UART connection safely."""
        with self._lock:
            self.close()
            self.open()

    def __enter__(self) -> "PicoUARTClient":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------
    def _log(self, message: str) -> None:
        """Print debug messages when debug mode is enabled."""
        if self.debug:
            print(f"[PicoUARTClient] {message}")

    def _require_serial(self) -> serial.Serial:
        """Return the active serial object or raise an error."""
        if self._ser is None or not self._ser.is_open:
            raise PicoTransportError("Serial port is not open")
        return self._ser

    def _drain_input(self, duration: float = 0.2) -> List[str]:
        """
        Drain any pending input lines for a short period.

        This is used for re-sync and startup cleanup.
        """
        ser = self._require_serial()
        drained: List[str] = []
        deadline = time.monotonic() + duration

        while time.monotonic() < deadline:
            try:
                raw = ser.readline()
            except serial.SerialException as exc:
                raise PicoTransportError(f"Serial read failed during drain: {exc}") from exc

            if not raw:
                time.sleep(0.005)
                continue

            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                drained.append(line)
                self._log(f"drain: {line}")

        return drained

    def resync(self, settle_time: float = 0.2) -> List[str]:
        """
        Re-synchronize the serial stream by draining pending lines.

        This does not assume any specific device command exists.
        """
        with self._lock:
            self._log("resync start")
            lines = self._drain_input(duration=settle_time)
            self._noise_lines.extend(lines)
            self._log(f"resync done, drained {len(lines)} line(s)")
            return lines

    def get_noise_lines(self) -> List[str]:
        """Return a copy of accumulated non-JSON/noise lines."""
        return list(self._noise_lines)

    # -------------------------------------------------------------------------
    # Parsing
    # -------------------------------------------------------------------------
    def _read_one_line(self) -> Optional[str]:
        """
        Read one line from UART.

        Returns:
          - str: decoded line without trailing newline
          - None: no line received within the read timeout
        """
        ser = self._require_serial()

        try:
            raw = ser.readline()
        except serial.SerialException as exc:
            raise PicoTransportError(f"Serial read failed: {exc}") from exc

        if not raw:
            return None

        line = raw.decode("utf-8", errors="replace").strip()
        self._log(f"rx raw: {line}")
        return line

    def _parse_json_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Parse a JSON line if possible.

        Non-JSON lines are treated as noise and returned as None.
        """
        if not line:
            return None

        if not line.startswith("{"):
            self._noise_lines.append(line)
            self._log(f"noise line: {line}")
            return None

        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            self._noise_lines.append(line)
            self._log(f"invalid json line: {line}")
            return None

        if not isinstance(obj, dict):
            self._noise_lines.append(line)
            self._log(f"json root is not object: {line}")
            return None

        return obj

    def _allocate_uart_request_id(self) -> int:
        """Allocate the next positive UART request ID.

        The caller must hold ``self._lock``.
        """
        request_id = self._next_uart_request_id
        self._next_uart_request_id += 1
        if self._next_uart_request_id > MAX_UART_REQUEST_ID:
            self._next_uart_request_id = 1
        return request_id

    def _is_matching_response(self, expected_request_id: int, obj: Dict[str, Any]) -> bool:
        """
        Check whether a received JSON object matches the request we are waiting for.
        """
        request_id = obj.get(UART_REQUEST_ID_FIELD)
        if isinstance(request_id, bool) or not isinstance(request_id, int):
            return False
        return request_id == expected_request_id

    # -------------------------------------------------------------------------
    # Core request-response
    # -------------------------------------------------------------------------
    def send_command(
        self,
        payload: Dict[str, Any],
        timeout: Optional[float] = None,
        resync_before_send: bool = False,
    ) -> Dict[str, Any]:
        """
        Send one JSON command and wait for the matching JSON response.

        Args:
            payload: JSON object to send. Must contain 'cmd'.
            timeout: Per-command timeout override.
            resync_before_send: Drain pending input before sending.

        Returns:
            Parsed JSON response object.

        Raises:
            PicoProtocolError, PicoTimeoutError, PicoTransportError
        """
        if not isinstance(payload, dict):
            raise PicoProtocolError("Command payload must be a dict")

        cmd = payload.get("cmd")
        if not isinstance(cmd, str) or not cmd.strip():
            raise PicoProtocolError("Command payload must contain non-empty 'cmd'")

        effective_timeout = self.command_timeout if timeout is None else timeout

        with self._lock:
            ser = self._require_serial()
            request_id = self._allocate_uart_request_id()
            request_payload = dict(payload)
            request_payload[UART_REQUEST_ID_FIELD] = request_id

            if resync_before_send:
                self._log("resync requested before send")
                self._drain_input(duration=0.2)

            try:
                message = json.dumps(request_payload, separators=(",", ":")) + "\n"
            except (TypeError, ValueError) as exc:
                raise PicoProtocolError(f"Failed to serialize JSON payload: {exc}") from exc

            self._log(f"tx: {message.strip()}")

            try:
                ser.write(message.encode("utf-8"))
                ser.flush()
            except serial.SerialTimeoutException as exc:
                raise PicoTransportError(f"Serial write timeout: {exc}") from exc
            except serial.SerialException as exc:
                raise PicoTransportError(f"Serial write failed: {exc}") from exc

            deadline = time.monotonic() + effective_timeout
            last_json_obj: Optional[Dict[str, Any]] = None

            while time.monotonic() < deadline:
                line = self._read_one_line()
                if line is None:
                    continue

                obj = self._parse_json_line(line)
                if obj is None:
                    continue

                last_json_obj = obj

                if self._is_matching_response(request_id, obj):
                    return obj

                # Keep unmatched JSON as noise-like diagnostic data.
                self._noise_lines.append(line)
                self._log(f"unmatched json response: {obj}")

            detail = {
                "expected_cmd": cmd,
                "expected_uart_request_id": request_id,
                "last_json_obj": last_json_obj,
            }
            raise PicoTimeoutError(f"Timed out waiting for response: {detail}")

    def _send_checked(
        self,
        payload: Dict[str, Any],
        expected_cmd: str,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a command and require a successful matching response."""
        response = self.send_command(payload, timeout=timeout)

        if response.get("ok") != 1:
            raise PicoProtocolError(f"Pico command failed: {response}")

        if response.get("cmd") != expected_cmd:
            raise PicoProtocolError(
                f"Unexpected command response: expected {expected_cmd}, "
                f"got {response.get('cmd')}"
            )

        return response

    @staticmethod
    def _validate_pins(pins: Sequence[int]) -> List[int]:
        """Validate channel numbers for ON/OFF commands."""
        if not pins:
            raise ValueError("pins must not be empty")

        validated = []
        for pin in pins:
            if isinstance(pin, bool) or not isinstance(pin, int):
                raise ValueError(f"pin must be integer: {pin!r}")
            if not 0 <= pin <= 255:
                raise ValueError(f"pin out of range: {pin}")
            validated.append(pin)

        return validated

    @staticmethod
    def _validate_pcf(which: Union[str, int]) -> Union[str, int]:
        """Validate a PCF selector accepted by PINSTAT/PCFSTAT."""
        if which == "ALL":
            return which
        if isinstance(which, bool) or not isinstance(which, int):
            raise ValueError("which must be 'ALL' or integer 0..15")
        if not 0 <= which <= 15:
            raise ValueError("pcf id out of range (0..15)")
        return which

    # -------------------------------------------------------------------------
    # High-level command helpers
    # -------------------------------------------------------------------------
    def echo(self, msg: Any, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Send ECHO command and return the JSON response."""
        return self.send_command(
            {
                "cmd": "ECHO",
                "msg": msg,
            },
            timeout=timeout,
        )

    def ping(self, timeout: Optional[float] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Basic health check using the Pico PING command.

        Returns:
            (True, response) on success
            (False, None) on failure
        """
        try:
            response = self._send_checked(
                {"cmd": "PING"},
                "PING",
                timeout=timeout,
            )
            if response.get("pong") != 1:
                raise PicoProtocolError(f"Missing or invalid pong field: {response}")
            return True, response
        except PicoClientError as exc:
            self._log(f"ping failed: {exc}")
            return False, None

    def on(self, pins: Sequence[int], timeout: Optional[float] = None) -> Dict[str, Any]:
        """Turn ON one or more channels."""
        validated = self._validate_pins(pins)
        return self._send_checked(
            {"cmd": "ON", "pins": validated},
            "ON",
            timeout=timeout,
        )

    def off(self, pins: Sequence[int], timeout: Optional[float] = None) -> Dict[str, Any]:
        """Turn OFF one or more channels."""
        validated = self._validate_pins(pins)
        return self._send_checked(
            {"cmd": "OFF", "pins": validated},
            "OFF",
            timeout=timeout,
        )

    def alloff(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Turn OFF all channels."""
        return self._send_checked(
            {"cmd": "ALLOFF"},
            "ALLOFF",
            timeout=timeout,
        )

    def route(self, pin: int, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Turn OFF all channels and then turn ON exactly one channel."""
        self._validate_pins([pin])
        self.alloff(timeout=timeout)
        return self.on([pin], timeout=timeout)

    def pinstat(
        self,
        which: Union[str, int] = "ALL",
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Return channel state for all channels or one PCF block."""
        selector = self._validate_pcf(which)
        response = self._send_checked(
            {"cmd": "PINSTAT", "which": selector},
            "PINSTAT",
            timeout=timeout,
        )
        pins = response.get("pins")
        expected_length = 256 if selector == "ALL" else 16
        if not isinstance(pins, list) or len(pins) != expected_length:
            raise PicoProtocolError(
                f"Invalid PINSTAT response: expected {expected_length} pins"
            )
        return response

    def pcfstat(
        self,
        which: Union[str, int] = "ALL",
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Return PCF presence for all chips or one chip."""
        selector = self._validate_pcf(which)
        response = self._send_checked(
            {"cmd": "PCFSTAT", "which": selector},
            "PCFSTAT",
            timeout=timeout,
        )
        present = response.get("present")
        if selector == "ALL":
            if not isinstance(present, list) or len(present) != 16:
                raise PicoProtocolError(
                    "Invalid PCFSTAT response: expected 16 presence values"
                )
        elif isinstance(present, bool) or not isinstance(present, int):
            raise PicoProtocolError(
                "Invalid PCFSTAT response: expected one presence value"
            )
        return response
