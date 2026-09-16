import threading
import time
import unittest

from PySide6.QtWidgets import QApplication

from qswitch_gui.model import RelayAddress
from qswitch_gui.ui.main_window import MainWindow


_APP = None


def _application():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


class FakeControllerClient:
    def __init__(self):
        self.mode = "normal"
        self.gui_lock = False
        self.system_lock = False
        self.gui_protected = set()
        self.system_protected = set()
        self.mode_calls = []
        self.lock_calls = []
        self.protection_calls = []
        self.relay_calls = []
        self.closed = set()
        self.fail_next_lock = False
        self.fail_next_protection = False
        self.refresh_started = threading.Event()
        self.release_refresh = threading.Event()
        self.block_first_refresh = True

    def snapshot(self):
        return {
            "identity": "simulator",
            "connected": True,
            "mode": self.mode,
            "gui_lock": self.gui_lock,
            "system_lock": self.system_lock,
            "gui_protected": sorted(self.gui_protected),
            "system_protected": sorted(self.system_protected),
            "state": sorted(self.closed),
        }

    def state(self):
        return self.snapshot()

    def refresh(self):
        if self.block_first_refresh:
            self.block_first_refresh = False
            self.refresh_started.set()
            self.release_refresh.wait(2)
        return self.snapshot()

    def set_mode(self, mode):
        self.mode_calls.append(mode)
        self.mode = mode
        self.gui_lock = mode == "gui_lock"
        self.system_lock = mode == "system_lock"
        return self.snapshot()

    def set_lock(self, lock, enabled):
        self.lock_calls.append((lock, enabled))
        if self.fail_next_lock:
            self.fail_next_lock = False
            raise RuntimeError("simulated lock failure")
        if lock == "gui":
            self.gui_lock = enabled
        else:
            self.system_lock = enabled
        self.mode = "system_lock" if self.system_lock else "gui_lock" if self.gui_lock else "normal"
        return self.snapshot()

    def set_protection(self, lines, system):
        lines = set(lines)
        self.protection_calls.append((sorted(lines), system))
        if self.fail_next_protection:
            self.fail_next_protection = False
            raise RuntimeError("simulated protection failure")
        if system:
            self.system_protected = lines
        else:
            self.gui_protected = lines
        return self.snapshot()

    def relay(self, signal, destination, close):
        self.relay_calls.append((signal, destination, close))
        address = f"{signal}!{destination}"
        if close:
            self.closed.add(address)
        else:
            self.closed.discard(address)
        return self.snapshot()


class PermissionGuiTests(unittest.TestCase):
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

    def test_global_lock_buttons_apply_immediately_and_refresh_is_observational(self):
        self.window.gui_lock_button.click()
        self._process_until(lambda: not self.window._busy)
        self.assertEqual(self.client.lock_calls, [("gui", True)])
        self.assertTrue(self.window.gui_lock_button.isChecked())
        self.assertEqual(self.window.controller_mode, "gui_lock")

        self.window.system_lock_button.click()
        self._process_until(lambda: not self.window._busy)
        self.assertEqual(self.client.lock_calls[-1], ("system", True))
        self.assertTrue(self.window.system_lock_button.isChecked())
        self.assertTrue(self.window.gui_lock_button.isChecked())

        self.window.refresh_state()
        self._process_until(lambda: not self.window._refresh_in_flight)
        self.assertEqual(self.client.lock_calls, [("gui", True), ("system", True)])
        self.assertEqual(self.window.permission_label.text(), "Permissions: GUI LOCK, SYSTEM LOCK")

        self.window.system_lock_button.click()
        self._process_until(lambda: not self.window._busy)
        self.window.gui_lock_button.click()
        self._process_until(lambda: not self.window._busy)
        self.assertEqual(self.client.lock_calls[-2:], [("system", False), ("gui", False)])
        self.assertEqual(self.window.permission_label.text(), "Permissions: NORMAL")

    def test_line_protection_buttons_apply_immediately(self):
        gui_button = self.window.matrix._protection_buttons[(3, False)]
        system_button = self.window.matrix._protection_buttons[(4, True)]
        gui_button.click()
        self._process_until(lambda: not self.window._busy)
        system_button.click()
        self._process_until(lambda: not self.window._busy)

        self.assertEqual(self.client.protection_calls, [([3], False), ([4], True)])
        self.assertTrue(gui_button.isChecked())
        self.assertTrue(system_button.isChecked())
        self.assertEqual(self.window.gui_protected, {3})
        self.assertEqual(self.window.system_protected, {4})

    def test_failed_lock_recovers_authoritative_state_without_false_active_state(self):
        self.window._show_error = lambda _title, _exc: None
        self.client.fail_next_lock = True
        self.window.gui_lock_button.click()
        self._process_until(lambda: not self.window._busy)
        self.assertFalse(self.window.gui_lock_button.isChecked())
        self.assertFalse(self.window.gui_lock)

    def test_failed_line_protection_recovers_authoritative_state(self):
        self.window._show_error = lambda _title, _exc: None
        self.client.fail_next_protection = True
        self.window.matrix._protection_buttons[(3, False)].click()
        self._process_until(lambda: not self.window._busy)
        self.assertFalse(self.window.matrix._protection_buttons[(3, False)].isChecked())
        self.assertEqual(self.window.gui_protected, set())

    def test_normal_relay_grid_interaction_still_works(self):
        address = RelayAddress(1, 1)
        self.window.matrix._buttons[address].click()
        self._process_until(lambda: not self.window._busy)
        self.assertEqual(self.client.relay_calls, [(1, 1, True)])
        self.assertTrue(self.window.state.is_closed(address))

    def test_refresh_does_not_issue_permission_mutations(self):
        self.window.refresh_state()
        self._process_until(self.client.refresh_started.is_set)
        self.client.release_refresh.set()
        self._process_until(lambda: not self.window._refresh_in_flight)
        self.assertEqual(self.client.lock_calls, [])
        self.assertEqual(self.client.protection_calls, [])


if __name__ == "__main__":
    unittest.main()
