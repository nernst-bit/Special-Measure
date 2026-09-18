from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Iterable

from qswitch_gui.device import QSwitchDevice
from qswitch_gui.event_log import EventLog
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
    gui_lock: bool
    system_lock: bool
    gui_protected: frozenset[int]
    system_protected: frozenset[int]


class QSwitchController:
    """The single command arbiter around the existing synchronous device API."""

    def __init__(self, device: QSwitchDevice, event_log: EventLog | None = None) -> None:
        self.device = device
        self.event_log = event_log or EventLog()
        self._lock = RLock()
        self.mode = PermissionMode.NORMAL
        self.gui_lock = False
        self.system_lock = False
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
                self.gui_lock,
                self.system_lock,
                frozenset(self.gui_protected),
                frozenset(self.system_protected),
            )

    def refresh_state(self) -> RelayState:
        with self._lock:
            return self.device.refresh_state()

    def set_mode(self, mode: PermissionMode) -> None:
        with self._lock:
            mode = PermissionMode(mode)
            previous = (self.gui_lock, self.system_lock, self.mode)
            self.gui_lock = mode is PermissionMode.GUI_LOCK
            self.system_lock = mode is PermissionMode.SYSTEM_LOCK
            self.mode = mode
            changes = (
                ("gui_lock", previous[0], self.gui_lock),
                ("system_lock", previous[1], self.system_lock),
            )
            try:
                for lock, old, new in changes:
                    if old != new:
                        self.event_log.record(lock, "api", True, "applied", enabled=new)
            except Exception:
                self.gui_lock, self.system_lock, self.mode = previous
                raise

    def set_lock(self, lock: str, enabled: bool) -> None:
        with self._lock:
            previous = (self.gui_lock, self.system_lock, self.mode)
            if lock == "gui":
                self.gui_lock = bool(enabled)
            elif lock == "system":
                self.system_lock = bool(enabled)
            else:
                raise ValueError("lock must be 'gui' or 'system'")
            self.mode = (
                PermissionMode.SYSTEM_LOCK
                if self.system_lock
                else PermissionMode.GUI_LOCK
                if self.gui_lock
                else PermissionMode.NORMAL
            )
            if (self.gui_lock, self.system_lock) != previous[:2]:
                try:
                    self.event_log.record(f"{lock}_lock", "api", True, "applied", enabled=bool(enabled))
                except Exception:
                    self.gui_lock, self.system_lock, self.mode = previous
                    raise

    def set_protection(self, lines: Iterable[int], *, system: bool) -> None:
        normalized = {int(line) for line in lines}
        if not normalized.issubset(set(range(1, 25))):
            raise ValueError("protected signal lines must be integers from 1 through 24")
        with self._lock:
            target = self.system_protected if system else self.gui_protected
            previous = set(target)
            target.clear()
            target.update(normalized)
            if previous != normalized:
                event = "system_protection" if system else "gui_protection"
                try:
                    self.event_log.record(
                        event,
                        "api",
                        True,
                        "applied",
                        protected_lines=sorted(normalized),
                    )
                except Exception:
                    target.clear()
                    target.update(previous)
                    raise

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
            actor = Actor(actor)
            try:
                for address in addresses:
                    self._authorize(address.signal, actor)
            except PermissionDeniedError as exc:
                self._record_rejection(
                    "relay_close" if close else "relay_open",
                    actor,
                    addresses=addresses,
                    reason=str(exc),
                )
                raise
            state = self.device.set_relays(addresses, close)
            self.event_log.record(
                "relay_close" if close else "relay_open",
                actor.value,
                True,
                "confirmed",
                relays=[address.scpi for address in addresses],
            )
            return state

    def reset(self, *, actor: Actor) -> RelayState:
        with self._lock:
            actor = Actor(actor)
            try:
                if self.system_lock:
                    raise PermissionDeniedError("system lock blocks RESET for every actor")
                if actor is Actor.GUI and self.gui_lock:
                    raise PermissionDeniedError("GUI/manual lock blocks GUI RESET")
                if self.system_protected:
                    raise PermissionDeniedError("system-protected lines make RESET unsafe")
                if actor is Actor.GUI and self.gui_protected:
                    raise PermissionDeniedError("GUI-protected lines make manual RESET unsafe")
            except PermissionDeniedError as exc:
                self._record_rejection("reset", actor, reason=str(exc))
                raise
            state = self.device.reset_to_default()
            self.event_log.record("reset", actor.value, True, "confirmed")
            return state

    def _record_rejection(self, event: str, actor: Actor, **details) -> None:
        if "addresses" in details:
            details["relays"] = [address.scpi for address in details.pop("addresses")]
        self.event_log.record(event, actor.value, False, "rejected", **details)

    def _authorize(self, signal: int, actor: Actor) -> None:
        actor = Actor(actor)
        if self.system_lock:
            raise PermissionDeniedError("system lock blocks all state-changing commands")
        if actor is Actor.GUI and self.gui_lock:
            raise PermissionDeniedError("GUI/manual lock blocks manual state-changing commands")
        if actor is Actor.GUI and signal in self.gui_protected:
            raise PermissionDeniedError(f"signal line {signal} is GUI-protected")
        if signal in self.system_protected:
            raise PermissionDeniedError(f"signal line {signal} is system-protected")
