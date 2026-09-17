import tempfile
import unittest
from pathlib import Path

from qswitch_gui.app import build_parser
from qswitch_gui.config import (
    DEFAULT_CONFIG_PATH,
    QSwitchConfigurationError,
    load_config,
)
from qswitch_gui.service import build_parser as build_service_parser, resolve_service_settings


class ConfigurationTests(unittest.TestCase):
    def test_default_ini_loads_expected_values(self):
        config = load_config()
        self.assertEqual(DEFAULT_CONFIG_PATH.name, "default.ini")
        self.assertEqual(config.controller_url, "http://127.0.0.1:8765")
        self.assertEqual(config.controller_port, 8765)
        self.assertEqual(config.serial_port, "")
        self.assertEqual(config.refresh_interval_ms, 2000)

    def test_cli_overrides_config_values(self):
        gui_args = build_parser().parse_args(["--controller-url", "http://localhost:9876"])
        config = load_config()
        self.assertEqual(gui_args.controller_url, "http://localhost:9876")

        service_args = build_service_parser().parse_args(["--port", "COM6", "--api-port", "9876"])
        serial_port, api_port = resolve_service_settings(
            config, service_args.port, service_args.api_port, service_args.demo
        )
        self.assertEqual(serial_port, "COM6")
        self.assertEqual(api_port, 9876)

    def test_controller_url_is_the_api_port_source(self):
        with self._config("http://127.0.0.1:9123", "COM6", "1500") as path:
            config = load_config(path)
        self.assertEqual(config.controller_port, 9123)
        self.assertEqual(resolve_service_settings(config, None, None, True)[1], 9123)

    def test_empty_serial_port_requires_service_override_unless_demo(self):
        config = load_config()
        with self.assertRaisesRegex(ValueError, "serial_port is empty"):
            resolve_service_settings(config, None, None, False)
        self.assertEqual(resolve_service_settings(config, None, None, True), ("", 8765))

    def test_malformed_relevant_configuration_fails_clearly(self):
        cases = (
            ("http://127.0.0.1", "COM6", "2000"),
            ("http://0.0.0.0:8765", "COM6", "2000"),
            ("http://127.0.0.1:8765", "COM6", "not-a-number"),
        )
        for controller_url, serial_port, refresh_interval in cases:
            with self.subTest(controller_url=controller_url, refresh_interval=refresh_interval):
                with self._config(controller_url, serial_port, refresh_interval) as path:
                    with self.assertRaises(QSwitchConfigurationError):
                        load_config(path)

    @staticmethod
    def _config(controller_url: str, serial_port: str, refresh_interval: str):
        class TemporaryConfig:
            def __enter__(self):
                self.directory = tempfile.TemporaryDirectory()
                self.path = Path(self.directory.name) / "default.ini"
                self.path.write_text(
                    "[MainGUI]\n"
                    f"refresh_interval_ms = {refresh_interval}\n\n"
                    "[Global.Controller]\n"
                    f"controller_url = {controller_url}\n\n"
                    "[Global.QSwitch]\n"
                    f"serial_port = {serial_port}\n",
                    encoding="utf-8",
                )
                return self.path

            def __exit__(self, exc_type, exc_value, traceback):
                self.directory.cleanup()

        return TemporaryConfig()


if __name__ == "__main__":
    unittest.main()
