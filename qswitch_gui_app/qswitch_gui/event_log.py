from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogError(RuntimeError):
    """Raised when a required controller change event cannot be persisted."""


def default_event_log_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "WangLab" / "QSwitch" / "events.jsonl"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "WangLab" / "QSwitch" / "events.jsonl"
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "wanglab-qswitch" / "events.jsonl"


class EventLog:
    """Small append-only JSON Lines audit log for controller mutations."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_event_log_path()

    def record(self, event: str, actor: str, success: bool, outcome: str, **details: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            "actor": actor,
            "success": success,
            "outcome": outcome,
            **details,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except (OSError, TypeError, ValueError) as exc:
            raise AuditLogError(f"Could not persist QSwitch audit event to {self.path}: {exc}") from exc
