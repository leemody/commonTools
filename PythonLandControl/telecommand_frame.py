import struct

class TelecommandFrame:
    """
    数据遥控帧结构
    包含:
    - 帧头 (5字节)
    - 数据 (变长，即 EPDU 数据包)
    - 校验码 (2字节, CRC16)
    """
    def __init__(self, data: bytes, header_bytes: bytes = b'\x1A\x2B\x3C\x4D\x5E'):
        """
        :param data: 帧数据区内容
        :param header_bytes: 5 字节的帧头内容
        """
        if len(header_bytes) != 5:
            raise ValueError(f"帧头必须是 5 个字节，当前为 {len(header_bytes)} 字节")
        self.header = header_bytes
        self.data = data
        
    def pack(self):
        """
        打包成完整帧：帧头 + 数据 + CRC校验码
        """
        # 1. 拼接帧头和数据
        frame_without_crc = self.header + self.data
        
        # 2. 计算 2 字节的 CRC 校验和
        crc_val = self.calculate_crc16(frame_without_crc)
        
        # 3. 将 CRC 转为 2 字节 (大端模式) 追加到末尾
        crc_bytes = struct.pack('>H', crc_val)
        
        return frame_without_crc + crc_bytes

    @classmethod
    def unpack(cls, frame_bytes: bytes):
        """
        逆运算：验证 CRC 校验和，并提取出有效的数据区
        """
        if len(frame_bytes) < 7: # 5字节头 + 2字节校验码 = 至少7字节
            raise ValueError(f"帧长度不足以包含帧头和校验码 ({len(frame_bytes)} 字节)")
            
        header = frame_bytes[:5]
        crc_bytes = frame_bytes[-2:]
        data = frame_bytes[5:-2]
        
        # CRC 校验
        expected_crc = cls.calculate_crc16(frame_bytes[:-2])
        received_crc = struct.unpack('>H', crc_bytes)[0]
        
        if expected_crc != received_crc:
            raise ValueError(f"CRC 校验失败: 期望 {hex(expected_crc)}, 实际收到 {hex(received_crc)}")
            
        return cls(data, header)

    @staticmethod
    def calculate_crc16(data: bytes) -> int:
        """
        常用的 CRC-16 校验算法 (这里采用标准的 CRC-16-CCITT / CCSDS 标准)
        多项式: 0x1021, 初始值: 0xFFFF
        如果下位机使用的是其他变种的 CRC 算法 (如 Modbus)，可以修改此处的初始值或多项式。
        """
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if (crc & 0x8000) != 0:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc = crc << 1
                crc &= 0xFFFF
        return crc
