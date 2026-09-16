# Wang Lab QSwitch GUI

A central Python controller service and Qt GUI for the Quantum Machines / QDevil QSwitch. The service owns the USB serial connection; the GUI and Special Measure are clients of the same serialized, state-verifying controller.

The GUI remains an individual package. The current hardware transport is USB serial; Ethernet/UDP is intentionally out of scope for this update.

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

Install dependencies from `qswitch_gui_app`:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -e '.[api,test]'
```

Start the one controller (replace `COM4` with the actual port):

```bash
python -m qswitch_gui.service --port COM4
```

Start the GUI in another terminal:

```bash
python -m qswitch_gui
```

If your checkout folder has another name, enter that folder and then `qswitch_gui_app`; the application does not depend on the repository's name.

No administrator privileges, MATLAB, NI-VISA, IDE, fixed COM number, or Unix runtime tool is required by this application. Windows normally supplies or downloads the QSwitch's Microchip MCP2221 USB serial driver. If it does not, use the driver source referenced by the QSwitch manual rather than an unverified driver.

## Connecting

1. Connect and power the QSwitch according to its manual, then attach its USB cable.
2. Start the controller with that port. It opens the port at 9600 baud, 8 data bits, no parity, one stop bit, no flow control, and LF termination.
3. Start the GUI. It connects to the controller URL and observes the controller's verified state; it never opens the hardware port in normal mode.

Click **Refresh Ports** after connecting or removing USB devices. The application never silently changes the selected device or reconnects to another port.

Stop the controller before a firmware updater or another hardware tool needs the COM port. MATLAB/Special Measure uses the controller API and does not open the COM port.

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
python -m qswitch_gui.service --demo
# in another terminal:
python -m qswitch_gui
```

The simulator service is stateful and exercises the same API, GUI refresh, permissions, and verification flow without hardware.

## Controller API

The small HTTP API is served on `http://127.0.0.1:8765` by default:

- `GET /health`, `GET /state`, `GET /identity`, `GET /error`
- `POST /state/refresh`
- `POST /relays/open` and `/relays/close` with `{"signal": 1, "destination": 3, "actor": "automation"}`
- `POST /reset` with `{"actor": "automation"}`
- `PUT /permissions/mode` with `{"mode": "normal"|"gui_lock"|"system_lock"}`
- `PUT /permissions/protection` with `{"lines": [1, 2], "system": false|true}`

`gui_lock` blocks GUI writes but permits automation. `system_lock` blocks all writes. GUI-only line protection blocks GUI writes to selected lines; system line protection blocks both actors. Protection changes do not move relays. RESET is conservative: it is blocked by system protection, and manual RESET is also blocked by GUI protection or GUI lock.

## Special Measure

The generator `instruments/create_sminst_QSwitch.m` creates the controller-backed instrument and includes the required `inst.datadim = zeros(6,1)` field. In MATLAB, start the Python controller, run `ind = smloadinst('QSwitch', [], 'none')`, then use the existing six selector channels through the normal Special Measure driver. Set `inst.data.controller_url` in the generated definition if the controller is not local. The MATLAB driver hides HTTP transport and waits for each controller response before the experiment continues.

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
