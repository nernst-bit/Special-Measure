from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Iterable

from qswitch_gui.device import QSwitchDevice
from qswitch_gui.model import RelayAddress, RelayState


class PermissionMode(str, Enum):
    NORMAL = "normal"
    GUI_LOCK = "gui_lock"
    SYSTEM_LOCK = "system_lock"


class Actor(str, Enum):
    GUI = "gui"
    AUTOMATION = "automation"


class PermissionDeniedError(RuntimeError):
    pass


@dataclass(frozen=True)
class ControllerSnapshot:
    identity: str | None
    connected: bool
    state: RelayState | None
    mode: PermissionMode
    gui_protected: frozenset[int]
    system_protected: frozenset[int]


class QSwitchController:
    """The single command arbiter around the existing synchronous device API."""

    def __init__(self, device: QSwitchDevice) -> None:
        self.device = device
        self._lock = RLock()
        self.mode = PermissionMode.NORMAL
        self.gui_protected: set[int] = set()
        self.system_protected: set[int] = set()

    def connect(self):
        with self._lock:
            return self.device.connect()

    def disconnect(self) -> None:
        with self._lock:
            self.device.disconnect()

    def snapshot(self) -> ControllerSnapshot:
        with self._lock:
            return ControllerSnapshot(
                self.device.identity,
                self.device.is_connected,
                self.device.confirmed_state,
                self.mode,
                frozenset(self.gui_protected),
                frozenset(self.system_protected),
            )

    def refresh_state(self) -> RelayState:
        with self._lock:
            return self.device.refresh_state()

    def set_mode(self, mode: PermissionMode) -> None:
        with self._lock:
            self.mode = PermissionMode(mode)

    def set_protection(self, lines: Iterable[int], *, system: bool) -> None:
        normalized = {int(line) for line in lines}
        if not normalized.issubset(set(range(1, 25))):
            raise ValueError("protected signal lines must be integers from 1 through 24")
        with self._lock:
            target = self.system_protected if system else self.gui_protected
            target.clear()
            target.update(normalized)

    def set_relay(self, address: RelayAddress, *, close: bool, actor: Actor) -> RelayState:
        return self.set_relays([address], close=close, actor=actor)

    def set_relays(self, addresses: list[RelayAddress], *, close: bool, actor: Actor) -> RelayState:
        with self._lock:
            if not addresses:
                raise ValueError("at least one relay address is required")
            if len(set(addresses)) != len(addresses):
                raise ValueError("relay addresses must be unique within one operation")
            # Authorize every line before delegating to the device, so a later
            # protected/locked address cannot produce a partial hardware write.
            for address in addresses:
                self._authorize(address.signal, actor)
            return self.device.set_relays(addresses, close)

    def reset(self, *, actor: Actor) -> RelayState:
        with self._lock:
            actor = Actor(actor)
            if self.mode is PermissionMode.SYSTEM_LOCK:
                raise PermissionDeniedError("system lock blocks RESET for every actor")
            if actor is Actor.GUI and self.mode is PermissionMode.GUI_LOCK:
                raise PermissionDeniedError("GUI/manual lock blocks GUI RESET")
            if self.system_protected:
                raise PermissionDeniedError("system-protected lines make RESET unsafe")
            if actor is Actor.GUI and self.gui_protected:
                raise PermissionDeniedError("GUI-protected lines make manual RESET unsafe")
            return self.device.reset_to_default()

    def _authorize(self, signal: int, actor: Actor) -> None:
        actor = Actor(actor)
        if self.mode is PermissionMode.SYSTEM_LOCK:
            raise PermissionDeniedError("system lock blocks all state-changing commands")
        if actor is Actor.GUI and self.mode is PermissionMode.GUI_LOCK:
            raise PermissionDeniedError("GUI/manual lock blocks manual state-changing commands")
        if actor is Actor.GUI and signal in self.gui_protected:
            raise PermissionDeniedError(f"signal line {signal} is GUI-protected")
        if signal in self.system_protected:
            raise PermissionDeniedError(f"signal line {signal} is system-protected")
