from __future__ import annotations

from datetime import datetime
from functools import partial

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qswitch_gui.device import (
    BreakoutLimitError,
    FakeSerialTransport,
    QSwitchDevice,
    SerialTransport,
    enumerate_serial_ports,
)
from qswitch_gui.model import BREAKOUT_RELAY_LIMIT, RelayAddress, RelayState

from .routing_matrix import RoutingMatrix
from .worker import Worker


class MainWindow(QMainWindow):
    protocol_line = Signal(str, str)

    def __init__(self, demo: bool = False) -> None:
        super().__init__()
        self.demo = demo
        self.device: QSwitchDevice | None = None
        self.state: RelayState | None = None
        self._busy = False
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(1)
        # Keep signal objects alive until their queued GUI callbacks have run.
        # QRunnable auto-deletion otherwise permits QObject cleanup on the pool
        # thread, which is unsafe for PySide6 on some native Qt platforms.
        self._workers: set[Worker] = set()
        self.setWindowTitle("Wang Lab QSwitch Controller" + (" — SIMULATED DEVICE" if demo else ""))
        self.resize(1120, 820)
        self.setMinimumSize(900, 650)
        self._build_ui()
        self._apply_style()
        self.protocol_line.connect(self.protocol_event)
        self.refresh_ports()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        if self.demo:
            banner = QLabel("SIMULATED DEVICE — NO HARDWARE COMMANDS WILL BE SENT")
            banner.setObjectName("simulationBanner")
            banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
            banner.setMinimumHeight(34)
            root.addWidget(banner)

        connection = QGroupBox("USB Serial Connection")
        connection_layout = QVBoxLayout(connection)
        controls = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(290)
        self.port_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.refresh_ports_button = QPushButton("Refresh Ports")
        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        controls.addWidget(self.port_combo, 1)
        controls.addWidget(self.refresh_ports_button)
        controls.addWidget(self.connect_button)
        controls.addWidget(self.disconnect_button)
        connection_layout.addLayout(controls)

        identity_row = QHBoxLayout()
        self.identity_label = QLabel("Device: Not connected")
        self.identity_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.connection_badge = QLabel("DISCONNECTED")
        self.connection_badge.setObjectName("connectionBadge")
        self.connection_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_badge.setMinimumWidth(128)
        identity_row.addWidget(self.identity_label, 1)
        identity_row.addWidget(self.connection_badge)
        connection_layout.addLayout(identity_row)
        root.addWidget(connection)

        title_row = QHBoxLayout()
        matrix_title = QLabel("Relay Routing Matrix — hardware-confirmed state")
        matrix_title.setObjectName("matrixTitle")
        self.breakout_label = QLabel(f"Breakout relays: unknown / {BREAKOUT_RELAY_LIMIT}")
        self.breakout_label.setObjectName("breakoutLabel")
        title_row.addWidget(matrix_title)
        title_row.addStretch()
        title_row.addWidget(self.breakout_label)
        root.addLayout(title_row)

        self.matrix = RoutingMatrix()
        root.addWidget(self.matrix, 1)

        actions = QHBoxLayout()
        self.refresh_state_button = QPushButton("Refresh State")
        self.reset_button = QPushButton("Reset to Default (Soft Ground)")
        self.reset_button.setObjectName("resetButton")
        actions.addWidget(self.refresh_state_button)
        actions.addStretch()
        actions.addWidget(self.reset_button)
        root.addLayout(actions)

        warning = QLabel(
            "Switch only with external signal voltages and currents at zero (QSwitch manual). "
            "This software cannot verify external electrical conditions. Soft ground is 1 MΩ."
        )
        warning.setObjectName("safetyWarning")
        warning.setWordWrap(True)
        root.addWidget(warning)

        status_frame = QFrame()
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("Status: Disconnected")
        self.status_label.setObjectName("statusLabel")
        self.protocol_log = QPlainTextEdit()
        self.protocol_log.setReadOnly(True)
        self.protocol_log.setMaximumBlockCount(300)
        self.protocol_log.setMaximumHeight(105)
        self.protocol_log.setPlaceholderText("Protocol log (timestamps, TX/RX, and events)")
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.protocol_log)
        root.addWidget(status_frame)
        self.setCentralWidget(central)

        self.refresh_ports_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.connect_device)
        self.disconnect_button.clicked.connect(self.disconnect_device)
        self.refresh_state_button.clicked.connect(self.refresh_state)
        self.reset_button.clicked.connect(self.confirm_reset)
        self.matrix.relay_clicked.connect(self.toggle_relay)
        self._update_controls()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f3f5f7; }
            QGroupBox { font-weight: 600; border: 1px solid #c6cdd4; border-radius: 5px; margin-top: 8px; padding-top: 9px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton { min-height: 28px; padding: 2px 12px; }
            #simulationBanner { color: #5b2600; background: #ffd58a; border: 2px solid #d16b00; font-weight: 800; }
            #connectionBadge { color: white; background: #5b6670; border-radius: 4px; padding: 5px 10px; font-weight: 700; }
            #matrixTitle { font-size: 14px; font-weight: 700; }
            #breakoutLabel { font-weight: 700; padding: 4px 8px; background: #e8edf2; border-radius: 4px; }
            #resetButton { color: #7a1818; font-weight: 700; }
            #safetyWarning { background: #fff4ce; border: 1px solid #e1c25a; padding: 7px; color: #4e3a00; }
            #statusLabel { font-weight: 600; }
            QToolButton[relayState="closed"] { color: #ffffff; background: #16734a; border: 1px solid #0d5535; border-radius: 3px; font-weight: 800; }
            QToolButton[relayState="open"] { color: #26323c; background: #ffffff; border: 1px solid #aab4bd; border-radius: 3px; font-weight: 700; }
            QToolButton[relayState="pending"] { color: #4e3600; background: #ffd66b; border: 1px solid #c08b00; border-radius: 3px; font-weight: 800; }
            QToolButton[relayState="unknown"] { color: #ffffff; background: #707981; border: 1px dashed #394149; border-radius: 3px; font-weight: 800; }
            """
        )

    def protocol_event(self, direction: str, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.protocol_log.appendPlainText(f"{stamp}  {direction:<5} {message}")

    def refresh_ports(self) -> None:
        selected = self.port_combo.currentData()
        self.port_combo.clear()
        if self.demo:
            self.port_combo.addItem("SIMULATED QSWITCH", "SIMULATED")
            self.protocol_event("INFO", "Demo mode: simulated port available")
            self._update_controls()
            return
        try:
            ports = enumerate_serial_ports()
        except Exception as exc:
            self._show_error("Port discovery failed", exc)
            return
        for port in ports:
            self.port_combo.addItem(port.label, port.device)
            index = self.port_combo.count() - 1
            metadata = [part for part in (port.manufacturer, port.serial_number) if part]
            self.port_combo.setItemData(index, " — ".join(metadata), Qt.ItemDataRole.ToolTipRole)
        if selected:
            index = self.port_combo.findData(selected)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        if not ports:
            self.port_combo.addItem("No serial ports found", None)
        self.protocol_event("INFO", f"Found {len(ports)} serial port(s)")
        self._update_controls()

    def connect_device(self) -> None:
        port = self.port_combo.currentData()
        if not port:
            self._show_error("Cannot connect", RuntimeError("Select an available serial port first."))
            return
        transport = (
            FakeSerialTransport(logger=self.protocol_line.emit)
            if self.demo
            else SerialTransport(str(port), logger=self.protocol_line.emit)
        )
        candidate = QSwitchDevice(transport)
        self._set_busy(True, "Connecting and reading actual relay state…")

        def connected(result: tuple[str, RelayState]) -> None:
            self.device = candidate
            identity, state = result
            self.identity_label.setText(f"Device: {identity}")
            self.connection_badge.setText("SIMULATED" if self.demo else "CONNECTED")
            self.connection_badge.setStyleSheet(
                "background: #a35400;" if self.demo else "background: #16734a;"
            )
            self._apply_confirmed_state(state)
            self._set_busy(False, f"Connected to {identity}; state confirmed from hardware")

        def failed(exc: Exception) -> None:
            candidate.disconnect()
            self._set_busy(False, "Connection failed")
            self._show_error("Could not connect to QSwitch", exc)

        self._run(candidate.connect, connected, failed)

    def disconnect_device(self) -> None:
        if self.device is None:
            return
        self.device.disconnect()
        self.device = None
        self.state = None
        self.identity_label.setText("Device: Not connected")
        self.connection_badge.setText("DISCONNECTED")
        self.connection_badge.setStyleSheet("background: #5b6670;")
        self.matrix.show_unknown()
        self.breakout_label.setText(f"Breakout relays: unknown / {BREAKOUT_RELAY_LIMIT}")
        self.protocol_event("INFO", "Serial port closed; available to other programs")
        self._set_status("Disconnected cleanly")
        self._update_controls()

    def refresh_state(self) -> None:
        if self.device is None:
            return
        self._set_busy(True, "Reading CLOSE:STATE? from QSwitch…")
        self._run(
            self.device.refresh_state,
            lambda state: (self._apply_confirmed_state(state), self._set_busy(False, "State refreshed and confirmed")),
            partial(self._operation_failed, "State refresh failed"),
        )

    def toggle_relay(self, address: RelayAddress) -> None:
        if self.device is None or self.state is None or self._busy:
            return
        close = not self.state.is_closed(address)
        action = "CLOSE" if close else "OPEN"
        if close and address.is_bnc and self.state.after_closing(address).breakout_count > BREAKOUT_RELAY_LIMIT:
            self._show_error(
                "Breakout relay limit",
                BreakoutLimitError(
                    f"The QSwitch manual allows no more than {BREAKOUT_RELAY_LIMIT} BNC breakout relays closed simultaneously."
                ),
            )
            return
        self._set_busy(True, f"{action} requested for Signal {address.signal} → {address.destination_name}; awaiting verification…")
        self.matrix.show_pending(address, action)

        def succeeded(state: RelayState) -> None:
            self._apply_confirmed_state(state)
            past = "closed" if close else "opened"
            self._set_busy(
                False,
                f"Signal {address.signal} → {address.destination_name} {past} and hardware-verified",
            )

        self._run(
            lambda: self.device.set_relay(address, close),
            succeeded,
            partial(self._operation_failed, f"Could not verify {action} {address.scpi}"),
        )

    def confirm_reset(self) -> None:
        if self.device is None:
            return
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Confirm QSwitch reset")
        dialog.setText("Reset the QSwitch to its documented default relay state?")
        dialog.setInformativeText(
            "• Signal lines 1–24 soft-grounded through 1 MΩ\n"
            "• All BNC breakout connections open\n"
            "• All IN connections open\n"
            "• QSwitch autosave turned OFF\n\n"
            "The manual recommends switching only with external signal voltages and currents at zero. "
            "This software cannot verify that condition."
        )
        dialog.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Reset)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if dialog.exec() != QMessageBox.StandardButton.Reset:
            return
        self._set_busy(True, "Reset in progress; awaiting *OPC? and state verification…")
        self._run(
            self.device.reset_to_default,
            lambda state: (self._apply_confirmed_state(state), self._set_busy(False, "Reset complete; documented default state verified")),
            partial(self._operation_failed, "Reset could not be verified"),
        )

    def _run(self, function, success, failure) -> None:
        worker = Worker(function)
        worker.setAutoDelete(False)
        worker.signals.succeeded.connect(success)
        worker.signals.failed.connect(failure)
        worker.signals.finished.connect(partial(self._worker_finished, worker))
        self._workers.add(worker)
        self.thread_pool.start(worker)

    def _worker_finished(self, worker: Worker) -> None:
        # This slot is queued to the GUI thread. Release the runnable and its
        # GUI-affine signal object only after success/failure callbacks finish.
        self._workers.discard(worker)
        worker.signals.deleteLater()

    def _operation_failed(self, title: str, exc: Exception) -> None:
        known_state = self.device.confirmed_state if self.device is not None else None
        if known_state is None:
            self.state = None
            self.matrix.show_unknown()
            self.breakout_label.setText(f"Breakout relays: unknown / {BREAKOUT_RELAY_LIMIT}")
        else:
            # A verification mismatch still supplies truthful actual hardware state.
            self._apply_confirmed_state(known_state)
        self._set_busy(False, title)
        self._show_error(title, exc)

    def _apply_confirmed_state(self, state: RelayState) -> None:
        self.state = state
        self.matrix.show_state(state, enabled=not self._busy)
        self.breakout_label.setText(f"Breakout relays: {state.breakout_count} / {BREAKOUT_RELAY_LIMIT}")

    def _set_busy(self, busy: bool, status: str) -> None:
        self._busy = busy
        self._set_status(status)
        self._update_controls()

    def _set_status(self, message: str) -> None:
        self.status_label.setText(f"Status: {message}")
        self.protocol_event("INFO", message)

    def _update_controls(self) -> None:
        connected = self.device is not None and self.device.is_connected
        port_available = bool(self.port_combo.currentData())
        self.port_combo.setEnabled(not connected and not self._busy)
        self.refresh_ports_button.setEnabled(not connected and not self._busy)
        self.connect_button.setEnabled(not connected and not self._busy and port_available)
        self.disconnect_button.setEnabled(connected and not self._busy)
        state_ready = connected and self.state is not None and not self._busy
        self.refresh_state_button.setEnabled(connected and not self._busy)
        self.reset_button.setEnabled(connected and not self._busy)
        self.matrix.set_controls_enabled(state_ready)

    def _show_error(self, title: str, exc: Exception) -> None:
        self.protocol_event("ERROR", f"{title}: {exc}")
        QMessageBox.critical(self, title, str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:
        self.thread_pool.waitForDone(7000)
        if self.device is not None:
            self.device.disconnect()
            self.protocol_event("INFO", "Serial port closed during application exit")
        event.accept()
