import threading
import unittest

from qswitch_gui.controller import Actor, PermissionDeniedError, PermissionMode, QSwitchController
from qswitch_gui.device import FakeSerialTransport, QSwitchDevice, StateVerificationError
from qswitch_gui.model import RelayAddress


def controller():
    transport = FakeSerialTransport()
    device = QSwitchDevice(transport)
    service = QSwitchController(device)
    service.connect()
    return service, transport


class ControllerPolicyTests(unittest.TestCase):
    def test_gui_lock_blocks_gui_but_allows_automation(self):
        service, _ = controller()
        address = RelayAddress(1, 1)
        service.set_mode(PermissionMode.GUI_LOCK)
        with self.assertRaises(PermissionDeniedError):
            service.set_relay(address, close=True, actor=Actor.GUI)
        service.set_relay(address, close=True, actor=Actor.AUTOMATION)
        self.assertTrue(service.snapshot().state.is_closed(address))

    def test_system_lock_blocks_both(self):
        service, _ = controller()
        service.set_mode(PermissionMode.SYSTEM_LOCK)
        for actor in Actor:
            with self.subTest(actor=actor), self.assertRaises(PermissionDeniedError):
                service.set_relay(RelayAddress(1, 1), close=True, actor=actor)

    def test_protection_is_permission_only_and_queries_remain_allowed(self):
        service, transport = controller()
        before = service.snapshot().state
        service.set_protection([2], system=False)
        with self.assertRaises(PermissionDeniedError):
            service.set_relay(RelayAddress(2, 1), close=True, actor=Actor.GUI)
        service.set_relay(RelayAddress(2, 1), close=True, actor=Actor.AUTOMATION)
        service.set_protection([2], system=True)
        with self.assertRaises(PermissionDeniedError):
            service.set_relay(RelayAddress(2, 1), close=False, actor=Actor.AUTOMATION)
        self.assertEqual(service.refresh_state(), service.snapshot().state)
        self.assertNotEqual(before, service.snapshot().state)
        self.assertIn("CLOSE:STATE?", transport.commands)

    def test_reset_is_conservative_with_protection(self):
        service, _ = controller()
        service.set_protection([1], system=True)
        with self.assertRaises(PermissionDeniedError):
            service.reset(actor=Actor.AUTOMATION)
        service.set_protection([], system=True)
        service.set_mode(PermissionMode.GUI_LOCK)
        with self.assertRaises(PermissionDeniedError):
            service.reset(actor=Actor.GUI)
        service.reset(actor=Actor.AUTOMATION)

    def test_concurrent_writes_are_serialized(self):
        service, _ = controller()
        errors = []
        addresses = [RelayAddress(n, 1) for n in range(1, 6)]
        def worker(address):
            try:
                service.set_relay(address, close=True, actor=Actor.AUTOMATION)
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=worker, args=(address,)) for address in addresses]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(errors, [])
        self.assertTrue(all(service.snapshot().state.is_closed(address) for address in addresses))

    def test_failed_verification_is_reported_by_controller(self):
        service, transport = controller()
        transport.ignore_next_switch = True
        with self.assertRaises(StateVerificationError):
            service.set_relay(RelayAddress(1, 1), close=True, actor=Actor.AUTOMATION)
        self.assertFalse(service.snapshot().state.is_closed(RelayAddress(1, 1)))


if __name__ == "__main__":
    unittest.main()
