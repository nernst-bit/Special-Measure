from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QToolButton

from qswitch_gui.model import RelayAddress, RelayState


DISPLAY_DESTINATIONS = (0, 9, 1, 2, 3, 4, 5, 6, 7, 8)
HEADERS = ("Ground\n1 MΩ", "IN", "BNC 1", "BNC 2", "BNC 3", "BNC 4", "BNC 5", "BNC 6", "BNC 7", "BNC 8")


class RoutingMatrix(QTableWidget):
    relay_clicked = Signal(object)

    def __init__(self) -> None:
        super().__init__(24, 10)
        self._buttons: dict[RelayAddress, QToolButton] = {}
        self.setHorizontalHeaderLabels(HEADERS)
        self.setVerticalHeaderLabels([f"Signal {line}" for line in range(1, 25)])
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.verticalHeader().setDefaultSectionSize(27)
        self.verticalHeader().setMinimumWidth(74)
        self.horizontalHeader().setMinimumSectionSize(63)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setMinimumSize(760, 450)

        for row, signal in enumerate(range(1, 25)):
            for column, destination in enumerate(DISPLAY_DESTINATIONS):
                address = RelayAddress(signal, destination)
                button = QToolButton()
                button.setMinimumHeight(23)
                button.clicked.connect(lambda _checked=False, a=address: self.relay_clicked.emit(a))
                self.setCellWidget(row, column, button)
                self._buttons[address] = button
        self.show_unknown()

    def show_state(self, state: RelayState, enabled: bool = True) -> None:
        for address, button in self._buttons.items():
            closed = state.is_closed(address)
            label = "CLOSED" if closed else "OPEN"
            button.setText("●" if closed else "○")
            button.setToolTip(
                f"Signal {address.signal} → {address.destination_name}: {label} (hardware confirmed)"
            )
            button.setAccessibleName(
                f"Signal {address.signal} to {address.destination_name}, {label}, hardware confirmed"
            )
            button.setEnabled(enabled)
            button.setProperty("relayState", label.lower())
            button.style().unpolish(button)
            button.style().polish(button)

    def show_unknown(self) -> None:
        for address, button in self._buttons.items():
            button.setText("?")
            button.setToolTip(f"Signal {address.signal} → {address.destination_name}: UNKNOWN")
            button.setAccessibleName(
                f"Signal {address.signal} to {address.destination_name}, unknown and unverified"
            )
            button.setEnabled(False)
            button.setProperty("relayState", "unknown")
            button.style().unpolish(button)
            button.style().polish(button)

    def show_pending(self, address: RelayAddress, action: str) -> None:
        button = self._buttons[address]
        button.setText("…")
        button.setToolTip(
            f"Signal {address.signal} → {address.destination_name}: {action} requested; verification pending"
        )
        button.setAccessibleName(
            f"Signal {address.signal} to {address.destination_name}, {action} pending verification"
        )
        button.setEnabled(False)
        button.setProperty("relayState", "pending")
        button.style().unpolish(button)
        button.style().polish(button)

    def set_controls_enabled(self, enabled: bool) -> None:
        for button in self._buttons.values():
            button.setEnabled(enabled)
