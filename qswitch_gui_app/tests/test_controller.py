import threading
import unittest

from qswitch_gui.controller import Actor, PermissionDeniedError, PermissionMode, QSwitchController
from qswitch_gui.device import BreakoutLimitError, FakeSerialTransport, QSwitchDevice, StateVerificationError
from qswitch_gui.model import RelayAddress, RelayState


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

    def test_batch_is_one_hardware_command(self):
        service, transport = controller()
        addresses = [RelayAddress(1, 1), RelayAddress(2, 1), RelayAddress(3, 9)]
        service.set_relays(addresses, close=True, actor=Actor.AUTOMATION)
        self.assertIn("CLOSE (@1!1,2!1,3!9)", transport.commands)
        self.assertEqual(transport.commands.count("CLOSE (@1!1,2!1,3!9)"), 1)
        self.assertTrue(all(service.snapshot().state.is_closed(address) for address in addresses))

    def test_batch_protection_rejection_has_no_hardware_write(self):
        service, transport = controller()
        service.set_protection([2], system=True)
        before = list(transport.commands)
        with self.assertRaises(PermissionDeniedError):
            service.set_relays([RelayAddress(1, 1), RelayAddress(2, 1)], close=True, actor=Actor.AUTOMATION)
        self.assertEqual(transport.commands, before)

    def test_batch_duplicate_rejection_has_no_hardware_write(self):
        service, transport = controller()
        before = list(transport.commands)
        address = RelayAddress(1, 1)
        with self.assertRaises(ValueError):
            service.set_relays([address, address], close=True, actor=Actor.AUTOMATION)
        self.assertEqual(transport.commands, before)

    def test_batch_bnc_limit_rejection_has_no_hardware_write(self):
        existing = [RelayAddress(signal, 1) for signal in range(1, 21)] + [RelayAddress(signal, 2) for signal in range(1, 21)]
        transport = FakeSerialTransport(state=RelayState(existing))
        service = QSwitchController(QSwitchDevice(transport))
        service.connect()
        before = list(transport.commands)
        with self.assertRaises(BreakoutLimitError):
            service.set_relays([RelayAddress(21, 1), RelayAddress(22, 2)], close=True, actor=Actor.AUTOMATION)
        self.assertEqual(transport.commands, before + ["CLOSE:STATE?"])


if __name__ == "__main__":
    unittest.main()
