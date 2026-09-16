import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from qswitch_gui.client import QSwitchControllerClient


class ClientErrorTests(unittest.TestCase):
    def test_json_http_detail_is_preserved(self):
        error = HTTPError(
            "http://127.0.0.1:8765/relays/close",
            409,
            "Conflict",
            {},
            io.BytesIO(b'{"detail":"system lock blocks all state-changing commands"}'),
        )
        with patch("qswitch_gui.client.urlopen", side_effect=error), self.assertRaisesRegex(
            RuntimeError, "system lock blocks all state-changing commands"
        ):
            QSwitchControllerClient().relay(1, 1, True, actor="automation")

    def test_malformed_http_error_uses_status_fallback(self):
        error = HTTPError("http://127.0.0.1:8765/state", 503, "Unavailable", {}, io.BytesIO(b"not-json"))
        with patch("qswitch_gui.client.urlopen", side_effect=error), self.assertRaisesRegex(
            RuntimeError, "HTTP Error 503: Unavailable"
        ):
            QSwitchControllerClient().state()


if __name__ == "__main__":
    unittest.main()
