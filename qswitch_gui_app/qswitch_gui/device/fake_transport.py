from __future__ import annotations

import re
from collections.abc import Callable

from qswitch_gui.model import RelayState, default_relay_state

from .state_parser import compact_channel_list, parse_channel_list
from .transport import ProtocolLogger


class FakeSerialTransport:
    """Stateful QSwitch simulator used by tests and the explicit demo mode."""

    def __init__(
        self,
        *,
        identity: str = "Quantum Machines,QSwitch,SIMULATED,2.0",
        state: RelayState | None = None,
        logger: ProtocolLogger | None = None,
    ) -> None:
        self.identity = identity
        self.state = default_relay_state() if state is None else state
        self._logger = logger
        self._open = False
        self.commands: list[str] = []
        self.timeout_on: set[str] = set()
        self.malformed_state_response: str | None = None
        self.ignore_next_switch = False

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def write_line(self, command: str) -> None:
        self._require_open()
        self.commands.append(command)
        if self._logger:
            self._logger("TX", command)
        if command in self.timeout_on:
            raise TimeoutError(f"simulated timeout for {command}")
        if command == "*RST":
            self.state = default_relay_state()
            return
        match = re.fullmatch(r"(OPEN|CLOSE)\s+(\(.*\))", command)
        if match:
            if self.ignore_next_switch:
                self.ignore_next_switch = False
                return
            requested = parse_channel_list(match.group(2)).closed
            if match.group(1) == "CLOSE":
                self.state = RelayState((*self.state.closed, *requested))
            else:
                self.state = RelayState(self.state.closed.difference(requested))

    def query_line(self, command: str) -> str:
        self.write_line(command)
        if command == "*IDN?":
            response = self.identity
        elif command == "CLOSE:STATE?":
            response = self.malformed_state_response or compact_channel_list(self.state)
        elif command == "*OPC?":
            response = "1"
        else:
            raise RuntimeError(f"unsupported simulated query: {command}")
        if self._logger:
            self._logger("RX", response)
        return response

    def _require_open(self) -> None:
        if not self._open:
            raise RuntimeError("simulated serial port is not open")
