from __future__ import annotations

from qswitch_gui.controller import Actor, PermissionMode, QSwitchController
from qswitch_gui.model import RelayAddress


def snapshot_dict(controller: QSwitchController) -> dict:
    snap = controller.snapshot()
    return {
        "identity": snap.identity,
        "connected": snap.connected,
        "state": sorted(a.scpi for a in snap.state.closed) if snap.state else None,
        "mode": snap.mode.value,
        "gui_protected": sorted(snap.gui_protected),
        "system_protected": sorted(snap.system_protected),
    }


def create_app(controller: QSwitchController):
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as exc:
        raise RuntimeError("Install the API extra: pip install -e '.[api]'") from exc

    class RelayRequest(BaseModel):
        signal: int
        destination: int
        actor: Actor = Actor.AUTOMATION

    class ProtectionRequest(BaseModel):
        lines: list[int]
        system: bool = False

    class ModeRequest(BaseModel):
        mode: PermissionMode

    class ResetRequest(BaseModel):
        actor: Actor = Actor.AUTOMATION

    app = FastAPI(title="Wang Lab QSwitch Controller", version="1.0")

    def call(function):
        try:
            return function()
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/health")
    def health():
        return {"ok": True, "controller": "qswitch"}

    @app.get("/state")
    def state():
        return snapshot_dict(controller)

    @app.post("/state/refresh")
    def refresh():
        return call(lambda: (controller.refresh_state(), snapshot_dict(controller))[1])

    @app.get("/identity")
    def identity():
        return {"identity": controller.snapshot().identity}

    @app.get("/error")
    def error_status():
        return call(lambda: {"error": controller.device.error_status()})

    @app.post("/relays/open")
    def open_relay(request: RelayRequest):
        return call(lambda: _relay_response(controller, request, False))

    @app.post("/relays/close")
    def close_relay(request: RelayRequest):
        return call(lambda: _relay_response(controller, request, True))

    @app.post("/reset")
    def reset(request: ResetRequest):
        return call(lambda: (controller.reset(actor=request.actor), snapshot_dict(controller))[1])

    @app.put("/permissions/mode")
    def mode(request: ModeRequest):
        controller.set_mode(request.mode)
        return snapshot_dict(controller)

    @app.put("/permissions/protection")
    def protection(request: ProtectionRequest):
        return call(lambda: (_set_protection(controller, request), snapshot_dict(controller))[1])

    return app


def _relay_response(controller, request, close):
    address = RelayAddress(request.signal, request.destination)
    controller.set_relay(address, close=close, actor=request.actor)
    return snapshot_dict(controller)


def _set_protection(controller, request):
    controller.set_protection(request.lines, system=request.system)
