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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from PySide6.QtWidgets import QApplication

    from qswitch_gui.ui import MainWindow

    application = QApplication(sys.argv[:1])
    application.setApplicationName("Wang Lab QSwitch Controller")
    application.setOrganizationName("Wang Lab, UIUC")
    window = MainWindow(demo=args.demo)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
