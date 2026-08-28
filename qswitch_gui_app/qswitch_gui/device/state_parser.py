from __future__ import annotations

import re
from collections.abc import Iterable

from qswitch_gui.model import RelayAddress, RelayState


class StateParseError(ValueError):
    pass


_WRAPPER = re.compile(r"^\(\s*@\s*(.*?)\s*\)$")
_ADDRESS = re.compile(r"^(\d+)!([0-9])$")


def _address(text: str, response: str) -> RelayAddress:
    match = _ADDRESS.fullmatch(text.strip())
    if not match:
        raise StateParseError(f"invalid relay address in state response: {response!r}")
    try:
        return RelayAddress(int(match.group(1)), int(match.group(2)))
    except ValueError as exc:
        raise StateParseError(f"out-of-range relay address in state response: {response!r}") from exc


def parse_channel_list(response: str) -> RelayState:
    """Parse the complete compact response returned by CLOSE:STATE?."""
    normalized = response.strip()
    match = _WRAPPER.fullmatch(normalized)
    if not match:
        raise StateParseError(f"malformed QSwitch channel list: {response!r}")
    body = match.group(1).strip()
    if not body:
        return RelayState()

    relays: list[RelayAddress] = []
    for raw_entry in body.split(","):
        entry = raw_entry.strip()
        if not entry:
            raise StateParseError(f"empty entry in QSwitch channel list: {response!r}")
        endpoints = entry.split(":")
        if len(endpoints) > 2:
            raise StateParseError(f"invalid range in QSwitch channel list: {response!r}")
        first = _address(endpoints[0], response)
        last = first if len(endpoints) == 1 else _address(endpoints[1], response)
        # Manual section 5.1: ranges may vary only the signal-line coordinate.
        if first.destination != last.destination or first.signal > last.signal:
            raise StateParseError(f"unsupported relay range in state response: {response!r}")
        relays.extend(
            RelayAddress(signal, first.destination)
            for signal in range(first.signal, last.signal + 1)
        )
    if len(set(relays)) != len(relays):
        raise StateParseError(f"duplicate relay in state response: {response!r}")
    return RelayState(relays)


def format_channel_list(addresses: Iterable[RelayAddress]) -> str:
    ordered = sorted(set(addresses))
    if not ordered:
        return "(@)"
    return "(@" + ",".join(address.scpi for address in ordered) + ")"


def compact_channel_list(state: RelayState) -> str:
    """Compact a state for the simulator, using documented same-group ranges."""
    entries: list[str] = []
    by_destination: dict[int, list[int]] = {}
    for address in sorted(state.closed):
        by_destination.setdefault(address.destination, []).append(address.signal)
    for destination, signals in sorted(by_destination.items()):
        start = previous = signals[0]
        for signal in (*signals[1:], -1):
            if signal == previous + 1:
                previous = signal
                continue
            first = f"{start}!{destination}"
            entries.append(first if start == previous else f"{first}:{previous}!{destination}")
            start = previous = signal
    return "(@" + ",".join(entries) + ")"
