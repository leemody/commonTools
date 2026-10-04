import serial
from PyQt6.QtCore import QThread, pyqtSignal
import time

class SerialWorker(QThread):
    """
    A worker thread for handling serial communication.
    Reads data from the serial port and emits it.
    """
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_port = None
        self._is_running = False

    def run(self):
        """
        The main logic of the worker thread.
        """
        self._is_running = True
        try:
            self.serial_port = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"Serial port {self.port} opened successfully.")
        except serial.SerialException as e:
            self.error_occurred.emit(f"Error opening serial port: {e}")
            self._is_running = False
            return

        while self._is_running:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    self.data_received.emit(data)
                else:
                    # Sleep briefly to prevent high CPU usage when no data is coming
                    time.sleep(0.01)
            except serial.SerialException as e:
                self.error_occurred.emit(f"Serial error: {e}")
                self._is_running = False

        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            print(f"Serial port {self.port} closed.")

    def stop(self):
        """
        Signals the thread to stop.
        """
        self._is_running = False
        self.wait() # Wait for the thread to finish cleanly
