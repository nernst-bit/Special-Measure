from __future__ import annotations

from dataclasses import dataclass

from .transport import ProtocolLogger


class SerialDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str
    manufacturer: str | None = None
    serial_number: str | None = None

    @property
    def label(self) -> str:
        description = self.description.strip()
        return f"{self.device} — {description}" if description and description != "n/a" else self.device


def enumerate_serial_ports() -> list[PortInfo]:
    try:
        from serial.tools import list_ports
    except ImportError as exc:
        raise SerialDependencyError("pyserial is not installed") from exc
    return sorted(
        (
            PortInfo(
                device=port.device,
                description=port.description or "",
                manufacturer=port.manufacturer,
                serial_number=port.serial_number,
            )
            for port in list_ports.comports()
        ),
        key=lambda port: port.device.casefold(),
    )


class SerialTransport:
    """Bounded line-oriented USB serial transport for the QSwitch."""

    def __init__(self, port: str, timeout: float = 2.0, logger: ProtocolLogger | None = None) -> None:
        self.port = port
        self.timeout = timeout
        self._logger = logger
        self._serial = None

    @property
    def is_open(self) -> bool:
        return bool(self._serial is not None and self._serial.is_open)

    def open(self) -> None:
        if self.is_open:
            return
        try:
            import serial
        except ImportError as exc:
            raise SerialDependencyError("pyserial is not installed") from exc
        # Manual section 4.4.1: fixed 9600 baud, 8 data bits, no parity,
        # one stop bit, and no flow control. Section 4.4 permits LF termination.
        self._serial = serial.Serial(
            port=self.port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

    def write_line(self, command: str) -> None:
        self._require_open()
        if len(command) > 127:
            raise ValueError("QSwitch command exceeds the manual's 127-character limit")
        if self._logger:
            self._logger("TX", command)
        self._serial.write(command.encode("ascii") + b"\n")
        self._serial.flush()

    def query_line(self, command: str) -> str:
        self.write_line(command)
        raw = self._serial.read_until(b"\n")
        if not raw.endswith(b"\n"):
            raise TimeoutError(f"QSwitch timed out waiting for response to {command}")
        try:
            response = raw.rstrip(b"\r\n").decode("ascii")
        except UnicodeDecodeError as exc:
            raise RuntimeError("QSwitch returned a non-ASCII response") from exc
        if self._logger:
            self._logger("RX", response)
        return response

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def _require_open(self) -> None:
        if not self.is_open:
            raise RuntimeError("serial port is not open")
