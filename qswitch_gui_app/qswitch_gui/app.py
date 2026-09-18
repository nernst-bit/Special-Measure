from __future__ import annotations

import argparse
import sys

from qswitch_gui.config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wang Lab QSwitch USB controller")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use an obvious simulated QSwitch; never opens a real serial port",
    )
    parser.add_argument(
        "--controller-url",
        default=None,
        help="central controller URL (overrides config.ini)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    from PySide6.QtWidgets import QApplication

    from qswitch_gui.ui import MainWindow

    application = QApplication(sys.argv[:1])
    application.setApplicationName("Wang Lab QSwitch Controller")
    application.setOrganizationName("Wang Lab, UIUC")
    # --demo is an explicit no-hardware developer simulator. Normal operation
    # always uses the central controller client.
    window = MainWindow(
        demo=args.demo,
        controller_url=None if args.demo else (args.controller_url or config.controller_url),
        refresh_interval_ms=config.refresh_interval_ms,
    )
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
