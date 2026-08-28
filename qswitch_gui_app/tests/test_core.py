import sys
import types
import unittest
from unittest.mock import patch

from qswitch_gui.device import (
    BreakoutLimitError,
    DeviceIdentityError,
    FakeSerialTransport,
    QSwitchDevice,
    SerialTransport,
    StateParseError,
    StateVerificationError,
    format_channel_list,
    parse_channel_list,
)
from qswitch_gui.model import RelayAddress, RelayState, default_relay_state


def connected_device(transport=None):
    transport = transport or FakeSerialTransport()
    device = QSwitchDevice(transport)
    device.connect()
    return device, transport


class ResetIgnoringTransport(FakeSerialTransport):
    def write_line(self, command):
        if command == "*RST":
            self.commands.append(command)
            return
        super().write_line(command)


class StateParserTests(unittest.TestCase):
    def test_empty_states(self):
        for response in ("(@)", "( @ )"):
            with self.subTest(response=response):
                self.assertEqual(parse_channel_list(response).closed, frozenset())

    def test_default_range(self):
        self.assertEqual(parse_channel_list("(@1!0:24!0)"), default_relay_state())

    def test_individual_relays(self):
        expected = {RelayAddress(1, 0), RelayAddress(24, 9), RelayAddress(7, 3)}
        self.assertEqual(parse_channel_list("(@1!0,24!9,7!3)").closed, frozenset(expected))

    def test_multiple_ranges_and_groups(self):
        state = parse_channel_list("(@ 1!0:3!0, 20!9:24!9, 7!2 )")
        expected = [
            *(RelayAddress(n, 0) for n in range(1, 4)),
            *(RelayAddress(n, 9) for n in range(20, 25)), RelayAddress(7, 2),
        ]
        self.assertEqual(state.closed, frozenset(expected))

    def test_rejects_malformed_or_unsafe_responses(self):
        responses = (
            "1!0", "()", "(@1!0:2!1)", "(@24!0:1!0)", "(@25!0)",
            "(@1!10)", "(@1!0,,2!0)", "(@1!0,1!0)",
        )
        for response in responses:
            with self.subTest(response=response), self.assertRaises(StateParseError):
                parse_channel_list(response)

    def test_matrix_to_scpi_conversion(self):
        address = RelayAddress(12, 3)
        self.assertEqual((address.scpi, address.destination_name, address.is_bnc), ("12!3", "BNC 3", True))
        self.assertEqual(format_channel_list([address]), "(@12!3)")
        self.assertEqual(RelayAddress(4, 0).destination_name, "Soft Ground")
        self.assertEqual(RelayAddress(4, 9).destination_name, "IN")


class DeviceTests(unittest.TestCase):
    def test_connection_identity_and_initial_state(self):
        device, transport = connected_device()
        self.assertEqual(device.identity, "Quantum Machines,QSwitch,SIMULATED,2.0")
        self.assertEqual(device.confirmed_state, default_relay_state())
        self.assertEqual(transport.commands[:2], ["*IDN?", "CLOSE:STATE?"])

    def test_identity_rejection_closes_port(self):
        identities = (
            "Acme,OtherSwitch,1,1.0", "Quantum Machines,NotQSwitch,1,2.0",
            "Acme,QSwitch,1,2.0", "Quantum Machines,QSwitch,,2.0", "",
        )
        for identity in identities:
            with self.subTest(identity=identity):
                transport = FakeSerialTransport(identity=identity)
                device = QSwitchDevice(transport)
                with self.assertRaises(DeviceIdentityError):
                    device.connect()
                self.assertFalse(transport.is_open)
                self.assertIsNone(device.confirmed_state)

    def test_qdevil_identity_is_accepted(self):
        transport = FakeSerialTransport(identity="QDevil,QSwitch,123,2.0")
        device = QSwitchDevice(transport)
        identity, _ = device.connect()
        self.assertEqual(identity, "QDevil,QSwitch,123,2.0")

    def test_breakout_count_excludes_ground_and_in(self):
        state = RelayState([RelayAddress(1, 0), RelayAddress(1, 9), RelayAddress(1, 1), RelayAddress(2, 8)])
        self.assertEqual(state.breakout_count, 2)

    def test_refuses_forty_first_bnc_without_transmission(self):
        forty = [RelayAddress(signal, bnc) for bnc in (1, 2) for signal in range(1, 21)]
        device, transport = connected_device(FakeSerialTransport(state=RelayState(forty)))
        before = list(transport.commands)
        with self.assertRaises(BreakoutLimitError):
            device.set_relay(RelayAddress(21, 1), close=True)
        self.assertEqual(transport.commands, [*before, "CLOSE:STATE?"])
        self.assertNotIn("CLOSE (@21!1)", transport.commands)
        self.assertEqual(device.confirmed_state.breakout_count, 40)

    def test_duplicate_bnc_close_at_limit_is_allowed(self):
        forty = [RelayAddress(signal, bnc) for bnc in (1, 2) for signal in range(1, 21)]
        device, _ = connected_device(FakeSerialTransport(state=RelayState(forty)))
        self.assertEqual(device.set_relay(RelayAddress(1, 1), close=True).breakout_count, 40)

    def test_ground_and_in_do_not_consume_bnc_capacity(self):
        forty = [RelayAddress(signal, bnc) for bnc in (1, 2) for signal in range(1, 21)]
        device, _ = connected_device(FakeSerialTransport(state=RelayState(forty)))
        self.assertEqual(device.set_relay(RelayAddress(24, 0), close=True).breakout_count, 40)
        self.assertEqual(device.set_relay(RelayAddress(24, 9), close=True).breakout_count, 40)

    def test_groups_can_coexist_and_open_is_verified(self):
        device, _ = connected_device()
        addresses = [RelayAddress(3, 0), RelayAddress(3, 9), RelayAddress(3, 2)]
        for address in addresses:
            device.set_relay(address, close=True)
        self.assertTrue(all(device.confirmed_state.is_closed(address) for address in addresses))
        state = device.set_relay(RelayAddress(3, 9), close=False)
        self.assertTrue(state.is_closed(RelayAddress(3, 0)))
        self.assertTrue(state.is_closed(RelayAddress(3, 2)))
        self.assertFalse(state.is_closed(RelayAddress(3, 9)))

    def test_failed_verification_never_becomes_confirmed(self):
        device, transport = connected_device()
        address = RelayAddress(1, 1)
        transport.ignore_next_switch = True
        with self.assertRaises(StateVerificationError):
            device.set_relay(address, close=True)
        self.assertFalse(device.confirmed_state.is_closed(address))
        self.assertEqual(transport.commands[-3:], ["CLOSE (@1!1)", "*OPC?", "CLOSE:STATE?"])

    def test_command_timeout_makes_state_unknown(self):
        device, transport = connected_device()
        transport.timeout_on.add("*OPC?")
        with self.assertRaises(TimeoutError):
            device.set_relay(RelayAddress(1, 1), close=True)
        self.assertIsNone(device.confirmed_state)

    def test_malformed_refresh_makes_state_unknown(self):
        device, transport = connected_device()
        transport.malformed_state_response = "not-a-channel-list"
        with self.assertRaises(StateParseError):
            device.refresh_state()
        self.assertIsNone(device.confirmed_state)

    def test_unknown_state_blocks_switching(self):
        device, transport = connected_device()
        device.confirmed_state = None
        before = list(transport.commands)
        with self.assertRaisesRegex(RuntimeError, "unknown"):
            device.set_relay(RelayAddress(1, 1), close=True)
        self.assertEqual(transport.commands, before)

    def test_disconnect_releases_transport(self):
        device, transport = connected_device()
        device.disconnect()
        self.assertFalse(transport.is_open)
        self.assertIsNone(device.identity)
        self.assertIsNone(device.confirmed_state)

    def test_reset_synchronizes_and_verifies_default(self):
        initial = RelayState([RelayAddress(4, 2), RelayAddress(5, 9)])
        device, transport = connected_device(FakeSerialTransport(state=initial))
        self.assertEqual(device.reset_to_default(), default_relay_state())
        self.assertEqual(transport.commands[-3:], ["*RST", "*OPC?", "CLOSE:STATE?"])

    def test_reset_mismatch_preserves_actual_state(self):
        initial = RelayState([RelayAddress(4, 2)])
        device, _ = connected_device(ResetIgnoringTransport(state=initial))
        with self.assertRaises(StateVerificationError):
            device.reset_to_default()
        self.assertEqual(device.confirmed_state, initial)

    def test_expected_default_is_exact(self):
        state = default_relay_state()
        self.assertEqual(len(state.closed), 24)
        self.assertEqual(state.breakout_count, 0)
        self.assertTrue(all(address.destination == 0 for address in state.closed))

    def test_serial_transport_uses_manual_settings_and_lf(self):
        opened = {}

        class FakePort:
            is_open = True

            def __init__(self, **kwargs):
                opened.update(kwargs)
                self.writes = []

            def write(self, data):
                self.writes.append(data)

            def flush(self):
                pass

            def close(self):
                self.is_open = False

        serial_module = types.SimpleNamespace(
            EIGHTBITS=8,
            PARITY_NONE="N",
            STOPBITS_ONE=1,
            Serial=FakePort,
        )
        with patch.dict(sys.modules, {"serial": serial_module}):
            transport = SerialTransport("TEST_PORT", timeout=2.0)
            transport.open()
            transport.write_line("*IDN?")
        self.assertEqual(opened["port"], "TEST_PORT")
        self.assertEqual(opened["baudrate"], 9600)
        self.assertEqual((opened["bytesize"], opened["parity"], opened["stopbits"]), (8, "N", 1))
        self.assertFalse(opened["xonxoff"] or opened["rtscts"] or opened["dsrdtr"])
        self.assertEqual(transport._serial.writes, [b"*IDN?\n"])


if __name__ == "__main__":
    unittest.main()
