import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                             QHBoxLayout, QComboBox, QPushButton, QTextEdit,
                             QLabel, QLineEdit)
from PyQt6.QtCore import pyqtSlot

import serial.tools.list_ports
from serial_worker import SerialWorker

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telemetry Receiver")
        self.setGeometry(100, 100, 800, 600)

        # --- UI Elements ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Connection settings layout
        connection_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.refresh_ports()

        self.baud_rate_input = QLineEdit("9600")
        self.connect_button = QPushButton("Connect")
        self.connect_button.setCheckable(True)

        connection_layout.addWidget(QLabel("Port:"))
        connection_layout.addWidget(self.port_combo)
        connection_layout.addWidget(QLabel("Baud Rate:"))
        connection_layout.addWidget(self.baud_rate_input)
        connection_layout.addWidget(self.connect_button)

        # Data display
        self.data_display = QTextEdit()
        self.data_display.setReadOnly(True)
        self.data_display.setFontFamily("Courier")

        self.layout.addLayout(connection_layout)
        self.layout.addWidget(QLabel("Raw Received Data (Hex):"))
        self.layout.addWidget(self.data_display)

        # --- State ---
        self.serial_worker = None

        # --- Connections ---
        self.port_combo.activated.connect(self.refresh_ports)
        self.connect_button.toggled.connect(self.handle_connect_toggle)

    def refresh_ports(self):
        """Scans for available serial ports and updates the combo box."""
        if self.connect_button.isChecked():
            return # Don't refresh while connected
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in sorted(ports):
            self.port_combo.addItem(port.device)
        print("Refreshed COM ports.")

    @pyqtSlot(bool)
    def handle_connect_toggle(self, checked):
        if checked:
            port = self.port_combo.currentText()
            baud_rate_str = self.baud_rate_input.text()
            if not port:
                self.connect_button.setChecked(False)
                self.data_display.append("Error: No port selected.")
                return
            try:
                baud_rate = int(baud_rate_str)
            except ValueError:
                self.connect_button.setChecked(False)
                self.data_display.append(f"Error: Invalid baud rate '{baud_rate_str}'.")
                return

            self.connect_button.setText("Disconnect")
            self.port_combo.setEnabled(False)
            self.baud_rate_input.setEnabled(False)

            self.serial_worker = SerialWorker(port, baud_rate)
            self.serial_worker.data_received.connect(self.on_data_received)
            self.serial_worker.error_occurred.connect(self.on_error)
            self.serial_worker.start()
        else:
            if self.serial_worker:
                self.serial_worker.stop()
                self.serial_worker = None
            self.connect_button.setText("Connect")
            self.port_combo.setEnabled(True)
            self.baud_rate_input.setEnabled(True)

    @pyqtSlot(bytes)
    def on_data_received(self, data):
        hex_data = data.hex(' ').upper()
        self.data_display.append(hex_data)

    @pyqtSlot(str)
    def on_error(self, error_message):
        self.data_display.append(f"ERROR: {error_message}")
        # Automatically toggle back the button on error
        if self.connect_button.isChecked():
            self.connect_button.setChecked(False)

    def closeEvent(self, event):
        """Ensure the worker thread is stopped when closing the window."""
        if self.serial_worker:
            self.serial_worker.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
