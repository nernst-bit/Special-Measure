# Wang Lab QSwitch GUI

A focused desktop controller for the Quantum Machines / QDevil QSwitch. It connects over the QSwitch USB virtual serial port, displays the complete 24 × 10 relay matrix, switches individual relays, refreshes actual hardware state, and resets the instrument to its documented default state.

This is a standalone Python application. It does not require or communicate through MATLAB or Special Measure. Version 1 supports USB serial only; Ethernet/UDP is intentionally out of scope.

The application is intended for the Wang Lab Windows 11 computer. Development and the explicit simulator also work on macOS.

## Safety and device behavior

The device-specific behavior follows *QSwitch User Manual D22019-B00 (2025-03-21), firmware 2.0*:

- The QSwitch has 24 signal lines and 10 independently controlled relays per line: soft ground (`!0`), BNC 1–8 (`!1`–`!8`), and IN (`!9`). Multiple destinations may be connected at once.
- Soft ground is through **1 MΩ**. It is not a hard, zero-ohm ground.
- At most **40 BNC breakout relays** may be closed simultaneously. Ground and IN relays do not count toward this limit.
- Relay switching should normally be performed with external signal voltages and currents at zero to minimize transients. The GUI cannot detect or verify those external conditions.
- The QSwitch enclosure must be appropriately grounded and the included 9 V adapter should be used; consult the manual before hardware operation.
- The GUI never enables autosave. `*RST` turns autosave off according to the manual.

The displayed matrix is hardware-authoritative. A click becomes `PENDING`; the program sends the documented command, synchronizes with `*OPC?`, queries `CLOSE:STATE?`, and only then displays a confirmed `OPEN` or `CLOSED` state. A timeout or unparseable response produces `UNKNOWN`, not an assumed success.

## Windows 11 setup (Git Bash)

Install 64-bit Python 3.10 or newer from Python.org if it is not already available. During installation, enable the option to add Python to `PATH`.

From Git Bash after cloning or pulling the repository:

```bash
git clone --branch qswitch-driver https://github.com/nernst-bit/Special-Measure.git
cd Special-Measure/qswitch_gui_app
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m qswitch_gui
```

If your checkout folder has another name, enter that folder and then `qswitch_gui_app`; the application does not depend on the repository's name.

No administrator privileges, MATLAB, NI-VISA, IDE, fixed COM number, or Unix runtime tool is required by this application. Windows normally supplies or downloads the QSwitch's Microchip MCP2221 USB serial driver. If it does not, use the driver source referenced by the QSwitch manual rather than an unverified driver.

## Connecting

1. Connect and power the QSwitch according to its manual, then attach its USB cable.
2. Start the GUI and select the appropriate entry, such as `COM3 — USB Serial Device`. Port labels come from pyserial's normal Windows port enumeration; all serial devices may appear.
3. Click **Connect**. The program opens only the selected port at 9600 baud, 8 data bits, no parity, one stop bit, no flow control, with LF termination and bounded two-second reads/writes.
4. The program queries `*IDN?`. It refuses to operate unless the second identity field is `QSwitch`.
5. It then queries `CLOSE:STATE?` before enabling any routing control.

Click **Refresh Ports** after connecting or removing USB devices. The application never silently changes the selected device or reconnects to another port.

Click **Disconnect** before MATLAB, Special Measure, a terminal, a firmware updater, or another program needs the COM port. Closing the window also closes the serial port.

## Controls

Each compact matrix cell is one physical relay. Column order is Ground, IN, then BNC 1–8 for usability; the SCPI identities remain `!0`, `!9`, and `!1`–`!8` respectively.

- `●` / green: CLOSED and confirmed from hardware
- `○` / white: OPEN and confirmed from hardware
- `…` / amber: requested command pending hardware verification
- `?` / gray: UNKNOWN or unverified; routing is disabled until state can be refreshed

Tooltips and accessible names also state the relay and status, so the display does not rely on color alone.

**Refresh State** re-reads the complete hardware state. The breakout counter is derived only from confirmed BNC relay state. If state is unknown, safety-dependent closes are refused until refresh succeeds.

**Reset to Default (Soft Ground)** requires confirmation, sends `*RST`, synchronizes with `*OPC?`, and verifies the reply from `CLOSE:STATE?`. The documented expected result is all 24 soft-ground relays closed, all BNC relays open, all IN relays open, and autosave off. If the reported relay state differs, the GUI warns and displays the actual reported state rather than claiming success.

The small timestamped protocol log records TX, RX, status, and error events for first-hardware debugging. Ordinary operation does not accept raw SCPI input.

## Simulator (macOS or Windows)

Install dependencies as above, then start the explicit simulator:

```bash
python -m qswitch_gui --demo
```

The window carries a prominent orange `SIMULATED DEVICE` banner and uses no real serial port. Normal `python -m qswitch_gui` never activates simulation automatically.

## Tests

Install the test extra and run:

```bash
pip install -e '.[test]'
pytest
```

The backend and simulator are independent of Qt, so device/parser tests require no QSwitch. The physical hardware has not been tested by this Python project yet.

## Troubleshooting

**No COM port appears**

- Confirm QSwitch power and USB connections, click **Refresh Ports**, and check Windows Device Manager under **Ports (COM & LPT)**.
- Try a known data-capable USB cable/port. If Windows does not install the device, follow the MCP2221 driver guidance in the QSwitch manual.

**Port busy / access denied**

- Close MATLAB, Special Measure, serial terminals, firmware tools, or another copy of this GUI, then retry. Only one program can own the COM port at a time.

**Device does not identify as QSwitch**

- Disconnect in the GUI, verify the selected COM port in Device Manager, then select the correct device. The application intentionally refuses an unknown instrument.

**Timeout or malformed state response**

- The GUI marks state unknown and does not claim the requested switch occurred. Check power/USB, disconnect and reconnect, then use **Refresh State**. The protocol log shows the last TX/RX exchange.
- Do not continue safety-dependent routing until actual state can be read. If problems persist, use a terminal only after disconnecting this GUI and follow the manual's exact serial settings.

## Source layout

```text
qswitch_gui/
  app.py, __main__.py
  device/       serial transport, SCPI parser, device API, simulator
  model/        relay identities and complete confirmed state
  ui/           Qt main window, routing matrix, worker
tests/          hardware-free parser and device tests
```

The device API is synchronous and testable. The GUI schedules it on one Qt worker thread so serial timeouts do not freeze normal UI interaction and operations cannot overlap.
