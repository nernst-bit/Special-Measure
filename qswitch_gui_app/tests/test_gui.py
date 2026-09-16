import threading
import time
import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from qswitch_gui.ui.main_window import MainWindow


_APP = None


def _application():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class FakeControllerClient:
    def __init__(self):
        self.mode = "normal"
        self.mode_calls = []
        self.gui_protected = set()
        self.system_protected = set()
        self.protection_calls = []
        self.refresh_started = threading.Event()
        self.release_refresh = threading.Event()
        self.block_first_refresh = True

    def snapshot(self):
        return {
            "identity": "simulator",
            "connected": True,
            "mode": self.mode,
            "gui_protected": sorted(self.gui_protected),
            "system_protected": sorted(self.system_protected),
            "state": [],
        }

    def refresh(self):
        if self.block_first_refresh:
            self.block_first_refresh = False
            self.refresh_started.set()
            self.release_refresh.wait(2)
        return self.snapshot()

    def set_mode(self, mode):
        self.mode_calls.append(mode)
        self.mode = mode
        return self.snapshot()

    def set_protection(self, lines, system):
        lines = set(lines)
        self.protection_calls.append((sorted(lines), system))
        if system:
            self.system_protected = lines
        else:
            self.gui_protected = lines
        return self.snapshot()


class PermissionModeGuiTests(unittest.TestCase):
    def setUp(self):
        _application()
        self.window = MainWindow(controller_url="http://simulator")
        self.client = FakeControllerClient()
        self.window.client = self.client
        self.window.controller_connected = True
        self.window._apply_snapshot(self.client.snapshot())
        self.window._update_controls()

    def tearDown(self):
        self.client.release_refresh.set()
        self.window.close()

    def _process_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _APP.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("timed out waiting for GUI worker")

    def _apply_mode(self, mode):
        self.window.mode_combo.setCurrentIndex(self.window.mode_combo.findData(mode))
        self.window.apply_mode_button.click()
        self._process_until(lambda: self.client.mode == mode and not self.window._busy)
        self.assertEqual(self.window.controller_mode, mode)

    def test_mode_apply_remains_available_during_refresh_and_all_transitions_work(self):
        self.window.refresh_state()
        self._process_until(self.client.refresh_started.is_set)

        # A timer/manual refresh is read-only and must not prevent the user's
        # mode request from entering the controller queue.
        self.window.mode_combo.setCurrentIndex(self.window.mode_combo.findData("system_lock"))
        self.assertTrue(self.window.apply_mode_button.isEnabled())
        self.window.apply_mode_button.click()
        self.client.release_refresh.set()
        self._process_until(lambda: self.client.mode_calls == ["system_lock"] and not self.window._busy)
        self.assertEqual(self.window.controller_mode, "system_lock")

        # A subsequent refresh must reflect the controller mode, not restore
        # the old normal-mode selection.
        self.window.refresh_state()
        self._process_until(lambda: not self.window._refresh_in_flight)
        self.assertEqual(self.window.mode_combo.currentData(), "system_lock")

        self._apply_mode("gui_lock")
        self._apply_mode("normal")
        self.assertEqual(self.client.mode_calls, ["system_lock", "gui_lock", "normal"])

    def test_refresh_preserves_pending_mode_until_apply_in_both_directions(self):
        self.window.mode_combo.setCurrentIndex(self.window.mode_combo.findData("system_lock"))
        self.window.refresh_state()
        self._process_until(self.client.refresh_started.is_set)
        self.client.release_refresh.set()
        self._process_until(lambda: not self.window._refresh_in_flight)

        self.assertEqual(self.window.controller_mode, "normal")
        self.assertEqual(self.window.mode_combo.currentData(), "system_lock")
        self.window.apply_mode_button.click()
        self._process_until(lambda: self.client.mode_calls == ["system_lock"] and not self.window._busy)
        self.assertEqual(self.window.controller_mode, "system_lock")

        self.window.mode_combo.setCurrentIndex(self.window.mode_combo.findData("normal"))
        self.window.refresh_state()
        self._process_until(lambda: not self.window._refresh_in_flight)
        self.assertEqual(self.window.controller_mode, "system_lock")
        self.assertEqual(self.window.mode_combo.currentData(), "normal")
        self.window.apply_mode_button.click()
        self._process_until(lambda: self.client.mode_calls == ["system_lock", "normal"] and not self.window._busy)
        self.assertEqual(self.window.controller_mode, "normal")

    def test_refresh_preserves_pending_line_protection_until_apply(self):
        item = self.window.gui_lines[1].item(0)
        item.setCheckState(Qt.CheckState.Checked)
        self.window.refresh_state()
        self._process_until(self.client.refresh_started.is_set)
        self.client.release_refresh.set()
        self._process_until(lambda: not self.window._refresh_in_flight)

        self.assertEqual(self.window.gui_lines[1].item(0).checkState().name, "Checked")
        self.assertEqual(self.window.client.gui_protected, set())
        self.window.apply_protection_button.click()
        self._process_until(lambda: not self.window._busy)
        self.assertIn(([1], False), self.client.protection_calls)
        self.assertEqual(self.client.gui_protected, {1})


if __name__ == "__main__":
    unittest.main()
