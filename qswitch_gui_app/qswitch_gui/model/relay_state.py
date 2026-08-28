from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# QSwitch manual section 3.2 / 6.2: 24 lines; !0 ground, !1-!8 BNC, !9 IN.
SIGNAL_LINES = range(1, 25)
DESTINATIONS = range(0, 10)
BNC_DESTINATIONS = range(1, 9)
BREAKOUT_RELAY_LIMIT = 40


@dataclass(frozen=True, order=True)
class RelayAddress:
    signal: int
    destination: int

    def __post_init__(self) -> None:
        if self.signal not in SIGNAL_LINES:
            raise ValueError("signal line must be an integer from 1 through 24")
        if self.destination not in DESTINATIONS:
            raise ValueError("destination must be an integer from 0 through 9")

    @property
    def is_bnc(self) -> bool:
        return self.destination in BNC_DESTINATIONS

    @property
    def scpi(self) -> str:
        return f"{self.signal}!{self.destination}"

    @property
    def destination_name(self) -> str:
        if self.destination == 0:
            return "Soft Ground"
        if self.destination == 9:
            return "IN"
        return f"BNC {self.destination}"


@dataclass(frozen=True)
class RelayState:
    """A complete hardware-confirmed set of closed relays."""

    closed: frozenset[RelayAddress]

    def __init__(self, closed: Iterable[RelayAddress] = ()) -> None:
        object.__setattr__(self, "closed", frozenset(closed))

    def is_closed(self, address: RelayAddress) -> bool:
        return address in self.closed

    @property
    def breakout_count(self) -> int:
        return sum(address.is_bnc for address in self.closed)

    def after_closing(self, address: RelayAddress) -> "RelayState":
        return RelayState((*self.closed, address))


def default_relay_state() -> RelayState:
    # Manual sections 3.2 and 6.1 (*RST): only all 24 soft-ground relays closed.
    return RelayState(RelayAddress(signal, 0) for signal in SIGNAL_LINES)
