from __future__ import annotations

from qswitch_gui.model import BREAKOUT_RELAY_LIMIT, RelayAddress, RelayState, default_relay_state

from .state_parser import format_channel_list, parse_channel_list
from .transport import Transport


class QSwitchError(RuntimeError):
    pass


class DeviceIdentityError(QSwitchError):
    pass


class BreakoutLimitError(QSwitchError):
    pass


class StateVerificationError(QSwitchError):
    pass


def is_qswitch_identity(identity: str) -> bool:
    fields = [field.strip() for field in identity.split(",")]
    if len(fields) < 4 or fields[1].casefold() != "qswitch":
        return False
    manufacturer = fields[0].casefold().replace("-", " ")
    recognized = "quantum machines" in manufacturer or "qdevil" in manufacturer
    return recognized and bool(fields[2]) and bool(fields[3])


class QSwitchDevice:
    """Synchronous, testable device API; callers choose how to schedule it."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self.identity: str | None = None
        self.confirmed_state: RelayState | None = None

    @property
    def is_connected(self) -> bool:
        return self.transport.is_open and self.identity is not None

    def connect(self) -> tuple[str, RelayState]:
        try:
            self.transport.open()
            identity = self.transport.query_line("*IDN?").strip()
            if not is_qswitch_identity(identity):
                raise DeviceIdentityError(
                    f"Instrument did not identify as a QSwitch: {identity or '<empty response>'}"
                )
            self.identity = identity
            state = self.refresh_state()
            return identity, state
        except Exception:
            self.identity = None
            self.confirmed_state = None
            self.transport.close()
            raise

    def disconnect(self) -> None:
        self.transport.close()
        self.identity = None
        self.confirmed_state = None

    def refresh_state(self) -> RelayState:
        self._require_connected_transport()
        try:
            state = parse_channel_list(self.transport.query_line("CLOSE:STATE?"))
        except Exception:
            self.confirmed_state = None
            raise
        self.confirmed_state = state
        return state

    def set_relay(self, address: RelayAddress, close: bool) -> RelayState:
        self._require_known_state()
        if close and address.is_bnc:
            # Re-read immediately before a safety-limited BNC close. The USB
            # port is exclusive, but the manual permits simultaneous LAN control.
            current = self.refresh_state()
            prospective = current.after_closing(address)
            if prospective.breakout_count > BREAKOUT_RELAY_LIMIT:
                raise BreakoutLimitError(
                    f"Closing {address.scpi} would exceed the 40 closed BNC-relay limit."
                )
        command = "CLOSE" if close else "OPEN"
        self._write_and_synchronize(f"{command} {format_channel_list([address])}")
        try:
            state = self.refresh_state()
        except Exception:
            self.confirmed_state = None
            raise
        if state.is_closed(address) != close:
            action = "closed" if close else "opened"
            raise StateVerificationError(
                f"QSwitch did not verify {address.scpi} as {action}; displayed state is the actual reply."
            )
        return state

    def reset_to_default(self) -> RelayState:
        self._require_connected_transport()
        self._write_and_synchronize("*RST")
        state = self.refresh_state()
        if state != default_relay_state():
            raise StateVerificationError(
                "Reset completed, but CLOSE:STATE? does not match the documented default state."
            )
        return state

    def _write_and_synchronize(self, command: str) -> None:
        try:
            self.transport.write_line(command)
            # Manual section 5.2: *OPC? may immediately follow a write and
            # returns 1 after the prior operation is fully complete.
            response = self.transport.query_line("*OPC?").strip()
            if response != "1":
                raise QSwitchError(f"Unexpected *OPC? response: {response!r}")
        except Exception:
            self.confirmed_state = None
            raise

    def _require_connected_transport(self) -> None:
        if not self.transport.is_open:
            raise QSwitchError("QSwitch is not connected")

    def _require_known_state(self) -> None:
        self._require_connected_transport()
        if self.confirmed_state is None:
            raise QSwitchError("Hardware state is unknown; refresh state before switching relays")
