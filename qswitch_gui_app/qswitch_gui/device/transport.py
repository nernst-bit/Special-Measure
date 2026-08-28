from __future__ import annotations

from typing import Callable, Protocol

ProtocolLogger = Callable[[str, str], None]


class Transport(Protocol):
    @property
    def is_open(self) -> bool: ...

    def open(self) -> None: ...

    def write_line(self, command: str) -> None: ...

    def query_line(self, command: str) -> str: ...

    def close(self) -> None: ...
