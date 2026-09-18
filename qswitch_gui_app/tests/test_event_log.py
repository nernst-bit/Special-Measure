import json
import tempfile
import unittest
from pathlib import Path

from qswitch_gui.controller import Actor, PermissionDeniedError, QSwitchController
from qswitch_gui.device import FakeSerialTransport, QSwitchDevice
from qswitch_gui.event_log import EventLog
from qswitch_gui.model import RelayAddress


class ControllerEventLogTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "events.jsonl"
        self.transport = FakeSerialTransport()
        self.controller = QSwitchController(
            QSwitchDevice(self.transport), event_log=EventLog(self.path)
        )
        self.controller.connect()

    def tearDown(self):
        self.tempdir.cleanup()

    def events(self):
        return [json.loads(line) for line in self.path.read_text().splitlines()]

    def test_successful_mutations_are_confirmed_and_retain_actor(self):
        address = RelayAddress(1, 1)
        self.controller.set_relay(address, close=True, actor=Actor.AUTOMATION)
        self.controller.set_relay(address, close=False, actor=Actor.GUI)
        self.controller.reset(actor=Actor.AUTOMATION)
        events = self.events()
        self.assertEqual([event["event"] for event in events], ["relay_close", "relay_open", "reset"])
        self.assertEqual(events[0]["actor"], "automation")
        self.assertEqual(events[0]["relays"], ["1!1"])
        self.assertTrue(all(event["success"] and event["outcome"] == "confirmed" for event in events))

    def test_lock_and_protection_changes_are_persisted(self):
        self.controller.set_lock("gui", True)
        self.controller.set_lock("system", True)
        self.controller.set_protection([3], system=False)
        self.controller.set_protection([4], system=True)
        events = self.events()
        self.assertEqual([event["event"] for event in events], [
            "gui_lock", "system_lock", "gui_protection", "system_protection"
        ])
        self.assertEqual(events[0]["enabled"], True)
        self.assertEqual(events[2]["protected_lines"], [3])
        self.assertEqual(events[3]["protected_lines"], [4])

    def test_rejected_mutation_is_distinguished_and_polling_is_not_logged(self):
        self.controller.set_lock("system", True)
        before = len(self.events())
        with self.assertRaises(PermissionDeniedError):
            self.controller.set_relay(RelayAddress(2, 1), close=True, actor=Actor.AUTOMATION)
        self.controller.refresh_state()
        events = self.events()
        self.assertEqual(len(events), before + 1)
        self.assertEqual(events[-1]["event"], "relay_close")
        self.assertFalse(events[-1]["success"])
        self.assertEqual(events[-1]["outcome"], "rejected")

    def test_log_appends_existing_history(self):
        self.path.write_text('{"event":"previous"}\n')
        self.controller.set_lock("gui", True)
        lines = self.path.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["event"], "previous")


if __name__ == "__main__":
    unittest.main()
