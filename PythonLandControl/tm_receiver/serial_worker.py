# 导入serial库用于串口通信，QThread和pyqtSignal用于PyQt的线程和信号机制，time库用于延时
import serial
from PyQt6.QtCore import QThread, pyqtSignal
import time
import random # 导入random库用于生成随机噪声
# 从uslp_parser模块导入UslpParser类和同步标记
from uslp_parser import UslpParser, USLP_SYNC_MARKER

class SerialWorker(QThread):
    """
    串口通信工作线程。
    增加了模拟模式，可以在没有物理串口的情况下生成和解析测试数据。
    """
    # 当一个完整的USLP帧被成功解析出来时，会发射此信号
    frame_received = pyqtSignal(bytes)
    # 当发生错误时，会发射此信号
    error_occurred = pyqtSignal(str)

    def __init__(self, port, baudrate):
        """
        构造函数。

        :param port: 串口号。如果为 "MOCK"，则启用模拟模式。
        :param baudrate: 波特率。在模拟模式下此参数被忽略。
        """
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_port = None
        self.uslp_parser = UslpParser()
        self._is_running = False
        # 检查是否启用模拟模式
        self.is_mock = (self.port == "MOCK")

    def run(self):
        """
        线程启动后自动执行的核心函数。
        根据是否为模拟模式，执行不同的逻辑。
        """
        self._is_running = True

        if self.is_mock:
            # 如果是模拟模式，则调用模拟数据生成函数
            self.run_mock_simulation()
        else:
            # 否则，调用真实的串口读取函数
            self.run_serial_read()

    def run_mock_simulation(self):
        """
        模拟数据生成和解析的逻辑。
        """
        print("启动模拟数据模式...")
        while self._is_running:
            # 1. 创建一个合法的USLP帧作为样本
            # *** 修改点: 按照用户要求，设置帧总长为1020字节 ***
            frame_length = 1020
            # USLP长度字段值为 长度-1
            vcid_and_length_field = (0 << 16) | (frame_length - 1)
            header = USLP_SYNC_MARKER + vcid_and_length_field.to_bytes(4, 'big')
            
            # 数据域长度为 1020 - 8 = 1012字节
            payload_length = frame_length - 8
            # 创建一个指定长度的载荷，用0填充
            payload = bytearray(payload_length)
            # 为了方便识别，可以在载荷的开头和结尾放一些可识别的数据
            payload[0:10] = b'MOCK_START'
            payload[-10:] = b'_MOCK_END_'
            
            # 完整的帧
            mock_frame = header + payload

            # 2. 模拟一些噪声数据，随机加在帧的前面
            noise = bytes([random.randint(0, 255) for _ in range(random.randint(0, 10))])
            
            # 3. 将带噪声的数据块送入解析器
            data_chunk = noise + mock_frame
            found_frames = self.uslp_parser.parse(data_chunk)

            # 4. 发射找到的帧
            for frame in found_frames:
                self.frame_received.emit(frame)

            # 5. 等待一段时间再发送下一帧
            time.sleep(1)
        print("模拟数据模式已停止。")

    def run_serial_read(self):
        """
        真实的串口数据读取逻辑。
        """
        print(f"尝试打开物理串口 {self.port}...")
        try:
            self.serial_port = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"串口 {self.port} 已成功打开。")
        except serial.SerialException as e:
            self.error_occurred.emit(f"打开串口时发生错误: {e}")
            self._is_running = False
            return

        while self._is_running:
            try:
                if self.serial_port.in_waiting > 0:
                    raw_data = self.serial_port.read(self.serial_port.in_waiting)
                    found_frames = self.uslp_parser.parse(raw_data)
                    for frame in found_frames:
                        self.frame_received.emit(frame)
                else:
                    time.sleep(0.01)
            except serial.SerialException as e:
                self.error_occurred.emit(f"串口读取错误: {e}")
                self._is_running = False

        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            print(f"串口 {self.port} 已关闭。")

    def stop(self):
        """
        请求停止线程。
        """
        self._is_running = False
        self.wait()
