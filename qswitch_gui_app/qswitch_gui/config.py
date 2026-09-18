from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.ini")
MIN_REFRESH_INTERVAL_MS = 500
MAX_REFRESH_INTERVAL_MS = 60000


class QSwitchConfigurationError(ValueError):
    """Raised when the QSwitch application configuration is missing or invalid."""


@dataclass(frozen=True)
class QSwitchConfig:
    controller_url: str
    controller_port: int
    serial_port: str
    refresh_interval_ms: int


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> QSwitchConfig:
    config_path = Path(path)
    parser = configparser.ConfigParser(interpolation=None)
    if not config_path.is_file():
        raise QSwitchConfigurationError(f"QSwitch configuration file not found: {config_path}")
    try:
        with config_path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error) as exc:
        raise QSwitchConfigurationError(f"Could not read QSwitch configuration {config_path}: {exc}") from exc

    controller_url = _required(parser, "Global.Controller", "controller_url", config_path)
    serial_port = _required(parser, "Global.QSwitch", "serial_port", config_path)
    refresh_text = _required(parser, "MainGUI", "refresh_interval_ms", config_path)
    controller_port = _controller_port(controller_url, config_path)
    try:
        refresh_interval_ms = int(refresh_text)
    except ValueError as exc:
        raise QSwitchConfigurationError(
            f"MainGUI.refresh_interval_ms must be an integer in "
            f"{MIN_REFRESH_INTERVAL_MS}..{MAX_REFRESH_INTERVAL_MS}: {refresh_text!r}"
        ) from exc
    if not MIN_REFRESH_INTERVAL_MS <= refresh_interval_ms <= MAX_REFRESH_INTERVAL_MS:
        raise QSwitchConfigurationError(
            f"MainGUI.refresh_interval_ms must be in {MIN_REFRESH_INTERVAL_MS}..{MAX_REFRESH_INTERVAL_MS}: "
            f"{refresh_interval_ms}"
        )
    return QSwitchConfig(controller_url, controller_port, serial_port, refresh_interval_ms)


def _required(parser: configparser.ConfigParser, section: str, key: str, path: Path) -> str:
    if not parser.has_section(section) or not parser.has_option(section, key):
        raise QSwitchConfigurationError(f"Missing required configuration [{section}] {key} in {path}")
    return parser.get(section, key).strip()


def _controller_port(controller_url: str, path: Path) -> int:
    try:
        parsed = urlsplit(controller_url)
    except ValueError as exc:
        raise QSwitchConfigurationError(f"Global.Controller.controller_url is malformed: {controller_url!r}") from exc
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise QSwitchConfigurationError(
            "Global.Controller.controller_url must use http(s) and a localhost hostname "
            f"in {path}: {controller_url!r}"
        )
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise QSwitchConfigurationError(
            f"Global.Controller.controller_url must be a plain localhost base URL: {controller_url!r}"
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise QSwitchConfigurationError(f"Global.Controller.controller_url has an invalid port: {controller_url!r}") from exc
    if port is None:
        raise QSwitchConfigurationError(f"Global.Controller.controller_url must include a port: {controller_url!r}")
    return port
