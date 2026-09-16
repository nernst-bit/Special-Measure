from __future__ import annotations

import json
from urllib.request import Request, urlopen


class QSwitchControllerClient:
    """Small standard-library client used by the GUI and MATLAB-facing helpers."""

    def __init__(self, base_url: str = "http://127.0.0.1:8765", timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, path: str, method: str = "GET", payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(self.base_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except Exception as exc:
            raise RuntimeError(f"QSwitch controller request {method} {path} failed: {exc}") from exc

    def state(self): return self.request("/state")
    def refresh(self): return self.request("/state/refresh", "POST")
    def relay(self, signal, destination, close, actor="gui"):
        action = "close" if close else "open"
        return self.request(f"/relays/{action}", "POST", {"signal": signal, "destination": destination, "actor": actor})
    def reset(self, actor="gui"): return self.request("/reset", "POST", {"actor": actor})
