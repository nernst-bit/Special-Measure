from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wang Lab QSwitch USB controller")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use an obvious simulated QSwitch; never opens a real serial port",
    )
    parser.add_argument(
        "--controller-url",
        default="http://127.0.0.1:8765",
        help="central controller URL (the default normal architecture)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="legacy direct USB mode; use only when no controller service is running",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from PySide6.QtWidgets import QApplication

    from qswitch_gui.ui import MainWindow

    application = QApplication(sys.argv[:1])
    application.setApplicationName("Wang Lab QSwitch Controller")
    application.setOrganizationName("Wang Lab, UIUC")
    window = MainWindow(demo=args.demo, controller_url=None if args.direct or args.demo else args.controller_url)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
