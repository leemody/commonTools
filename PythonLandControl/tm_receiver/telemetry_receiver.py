# 导入sys模块，用于处理Python运行时环境和交互
import sys
# 从PyQt6.QtWidgets导入GUI相关的类
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                             QHBoxLayout, QComboBox, QPushButton, QTextEdit,
                             QLabel, QLineEdit, QCheckBox)
# 从PyQt6.QtCore导入pyqtSlot，用于定义槽函数
from PyQt6.QtCore import pyqtSlot
# 导入pyserial工具，用于列出可用的串口
import serial.tools.list_ports
# 从当前目录下的serial_worker模块导入SerialWorker类
from serial_worker import SerialWorker

class MainWindow(QMainWindow):
    """
    应用程序的主窗口类。
    """
    def __init__(self):
        """
        主窗口的构造函数。
        """
        super().__init__()
        self.setWindowTitle("遥测数据接收器 (Telemetry Receiver)")
        self.setGeometry(100, 100, 800, 600)

        # --- 创建UI元素 ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        connection_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.baud_rate_input = QLineEdit("9600")
        self.mock_data_checkbox = QCheckBox("使用模拟数据")
        self.connect_button = QPushButton("连接 (Connect)")
        self.connect_button.setCheckable(True)

        connection_layout.addWidget(QLabel("串口 (Port):"))
        connection_layout.addWidget(self.port_combo)
        connection_layout.addWidget(QLabel("波特率 (Baud Rate):"))
        connection_layout.addWidget(self.baud_rate_input)
        connection_layout.addWidget(self.mock_data_checkbox)
        connection_layout.addWidget(self.connect_button)

        self.data_display = QTextEdit()
        self.data_display.setReadOnly(True)
        self.data_display.setFontFamily("Courier")

        self.layout.addLayout(connection_layout)
        self.layout.addWidget(QLabel("已解析的USLP帧 (Hex):"))
        self.layout.addWidget(self.data_display)

        # --- 状态变量 ---
        self.serial_worker = None

        # --- 信号与槽的连接 ---
        self.port_combo.activated.connect(self.refresh_ports)
        self.connect_button.toggled.connect(self.handle_connect_toggle)
        self.mock_data_checkbox.stateChanged.connect(self._update_ui_state)

        # --- 初始化UI状态 ---
        self.refresh_ports() # 这会填充列表并调用_update_ui_state

    def _update_ui_state(self):
        """
        根据当前状态（连接、模拟、串口可用性）集中更新所有UI控件的启用/禁用状态。
        """
        is_connected = self.connect_button.isChecked()
        is_mock_mode = self.mock_data_checkbox.isChecked()

        if is_connected:
            # 如果已连接，锁定所有设置
            self.port_combo.setEnabled(False)
            self.baud_rate_input.setEnabled(False)
            self.mock_data_checkbox.setEnabled(False)
        else:
            # 如果未连接，可以更改设置
            self.mock_data_checkbox.setEnabled(True)
            
            # 检查是否有可用的物理串口
            ports_available = self.port_combo.count() > 0 and "未检测到" not in self.port_combo.itemText(0)
            
            # 串口和波特率输入框仅在“非模拟模式”且“有可用串口”时可用
            self.port_combo.setEnabled(not is_mock_mode and ports_available)
            self.baud_rate_input.setEnabled(not is_mock_mode)
            
            # “连接”按钮在“模拟模式”或“有可用串口”时可用
            self.connect_button.setEnabled(is_mock_mode or ports_available)

    def refresh_ports(self):
        """扫描并刷新串口列表，然后更新UI状态。"""
        if self.connect_button.isChecked():
            return
        
        current_selection = self.port_combo.currentText()
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        
        if not ports:
            self.port_combo.addItem("未检测到串口")
        else:
            for port in sorted(ports):
                self.port_combo.addItem(port.device)
            # 尝试恢复之前的选择
            if current_selection in [self.port_combo.itemText(i) for i in range(self.port_combo.count())]:
                self.port_combo.setCurrentText(current_selection)

        print("已刷新可用串口列表。")
        # 刷新列表后，调用状态更新函数
        self._update_ui_state()

    @pyqtSlot(bool)
    def handle_connect_toggle(self, checked):
        """处理连接/断开按钮的点击事件。"""
        if checked:
            use_mock_data = self.mock_data_checkbox.isChecked()
            port = "MOCK" if use_mock_data else self.port_combo.currentText()
            baud_rate = 0 if use_mock_data else int(self.baud_rate_input.text() or 0)

            # 在启动worker之前，再次进行有效性检查
            if not use_mock_data and (not port or "未检测到" in port or baud_rate <= 0):
                self.data_display.append("错误: 请选择有效的串口和波特率。")
                self.connect_button.setChecked(False) # 立即弹回按钮
                return

            self.connect_button.setText("断开 (Disconnect)")
            self.serial_worker = SerialWorker(port, baud_rate)
            self.serial_worker.frame_received.connect(self.on_frame_received)
            self.serial_worker.error_occurred.connect(self.on_error)
            self.serial_worker.start()
        else:
            if self.serial_worker:
                self.serial_worker.stop()
                self.serial_worker = None
            self.connect_button.setText("连接 (Connect)")
        
        # 连接或断开后，都更新一次UI状态
        self._update_ui_state()

    @pyqtSlot(bytes)
    def on_frame_received(self, frame):
        """当接收到完整的USLP帧时被调用。"""
        hex_data = frame.hex(' ').upper()
        self.data_display.append(f"[OK] 接收到帧: {hex_data}")

    @pyqtSlot(str)
    def on_error(self, error_message):
        """当接收到错误信息时被调用。"""
        self.data_display.append(f"错误: {error_message}")
        if self.connect_button.isChecked():
            self.connect_button.setChecked(False)

    def closeEvent(self, event):
        """关闭窗口时确保后台线程被安全地停止。"""
        if self.serial_worker:
            self.serial_worker.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
