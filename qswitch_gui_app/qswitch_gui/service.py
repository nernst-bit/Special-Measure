from __future__ import annotations

import argparse

from qswitch_gui.api import create_app
from qswitch_gui.config import QSwitchConfig, load_config
from qswitch_gui.controller import QSwitchController
from qswitch_gui.device import FakeSerialTransport, QSwitchDevice, SerialTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single-owner localhost QSwitch controller service")
    parser.add_argument("--port", help="QSwitch serial port, for example COM4 (overrides default.ini)")
    parser.add_argument("--demo", action="store_true", help="serve the stateful simulator instead of hardware")
    parser.add_argument("--api-port", type=int, help="controller API port (overrides the port in default.ini)")
    return parser


def resolve_service_settings(config: QSwitchConfig, serial_port: str | None, api_port: int | None, demo: bool) -> tuple[str, int]:
    selected_port = serial_port or config.serial_port
    if not demo and not selected_port:
        raise ValueError("QSwitch serial_port is empty; set [Global.QSwitch] serial_port or pass --port")
    selected_api_port = config.controller_port if api_port is None else api_port
    if not 1 <= selected_api_port <= 65535:
        raise ValueError(f"controller API port must be in 1..65535: {selected_api_port}")
    return selected_port, selected_api_port


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config()
    try:
        serial_port, api_port = resolve_service_settings(config, args.port, args.api_port, args.demo)
    except ValueError as exc:
        parser.error(str(exc))
    transport = FakeSerialTransport() if args.demo else SerialTransport(serial_port)
    controller = QSwitchController(QSwitchDevice(transport))
    controller.connect()
    try:
        import uvicorn
        # This candidate intentionally serves only same-machine GUI/MATLAB clients.
        uvicorn.run(create_app(controller), host="127.0.0.1", port=api_port)
    finally:
        controller.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
