from __future__ import annotations

import argparse

from qswitch_gui.api import create_app
from qswitch_gui.controller import QSwitchController
from qswitch_gui.device import FakeSerialTransport, QSwitchDevice, SerialTransport


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Single-owner localhost QSwitch controller service")
    parser.add_argument("--port", help="QSwitch serial port, for example COM4")
    parser.add_argument("--demo", action="store_true", help="serve the stateful simulator instead of hardware")
    parser.add_argument("--api-port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not args.demo and not args.port:
        parser.error("--port is required unless --demo is used")
    transport = FakeSerialTransport() if args.demo else SerialTransport(args.port)
    controller = QSwitchController(QSwitchDevice(transport))
    controller.connect()
    try:
        import uvicorn
        # This candidate intentionally serves only same-machine GUI/MATLAB clients.
        uvicorn.run(create_app(controller), host="127.0.0.1", port=args.api_port)
    finally:
        controller.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
