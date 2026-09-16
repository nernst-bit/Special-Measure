import unittest

from fastapi.testclient import TestClient

from qswitch_gui.api import create_app
from qswitch_gui.controller import QSwitchController
from qswitch_gui.device import FakeSerialTransport, QSwitchDevice


class ApiSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeSerialTransport()
        self.controller = QSwitchController(QSwitchDevice(self.transport))
        self.controller.connect()
        self.client = TestClient(create_app(self.controller))

    def test_state_and_batch_are_exposed(self):
        response = self.client.get("/state")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "normal")
        response = self.client.post("/relays/batch/close", json={
            "relays": [{"signal": 1, "destination": 1}, {"signal": 2, "destination": 9}],
            "actor": "automation",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("1!1", response.json()["state"])
        self.assertIn("CLOSE (@1!1,2!9)", self.transport.commands)

    def test_gui_lock_allows_automation_but_not_gui(self):
        self.assertEqual(self.client.put("/permissions/mode", json={"mode": "gui_lock"}).status_code, 200)
        blocked = self.client.post("/relays/close", json={"signal": 3, "destination": 1, "actor": "gui"})
        self.assertEqual(blocked.status_code, 409)
        allowed = self.client.post("/relays/close", json={"signal": 3, "destination": 1, "actor": "automation"})
        self.assertEqual(allowed.status_code, 200)

    def test_system_lock_blocks_automation_and_protection_is_non_mutating(self):
        before = list(self.transport.commands)
        response = self.client.put("/permissions/protection", json={"lines": [4, 5], "system": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.transport.commands, before)
        self.assertEqual(self.client.put("/permissions/mode", json={"mode": "system_lock"}).status_code, 200)
        blocked = self.client.post("/relays/batch/close", json={
            "relays": [{"signal": 4, "destination": 1}, {"signal": 6, "destination": 1}],
            "actor": "automation",
        })
        self.assertEqual(blocked.status_code, 409)
        self.assertNotIn("CLOSE (@4!1,6!1)", self.transport.commands)

    def test_invalid_batch_is_rejected_before_hardware_write(self):
        before = list(self.transport.commands)
        response = self.client.post("/relays/batch/close", json={
            "relays": [{"signal": 1, "destination": 1}, {"signal": 25, "destination": 1}],
            "actor": "automation",
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.transport.commands, before)

    def test_reset_is_blocked_by_all_relevant_policies(self):
        for mode, actor in (("gui_lock", "gui"), ("system_lock", "automation")):
            with self.subTest(mode=mode):
                self.client.put("/permissions/mode", json={"mode": mode})
                before = list(self.transport.commands)
                response = self.client.post("/reset", json={"actor": actor})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(self.transport.commands, before)
                self.client.put("/permissions/mode", json={"mode": "normal"})

        for system, actor in ((False, "gui"), (True, "automation")):
            with self.subTest(system=system):
                self.client.put("/permissions/protection", json={"lines": [1], "system": system})
                before = list(self.transport.commands)
                response = self.client.post("/reset", json={"actor": actor})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(self.transport.commands, before)
                self.client.put("/permissions/protection", json={"lines": [], "system": system})


if __name__ == "__main__":
    unittest.main()
