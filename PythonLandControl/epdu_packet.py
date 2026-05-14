import json
from epdu_header import EpduHeader
from data_model import TargetData

class EpduPacket:
    """
    完整的 EPDU 包（包头 + 数据区）
    """
    def __init__(self, header: EpduHeader, payload: TargetData):
        self.header = header
        self.payload = payload

    def pack(self):
        """
        将数据区打包，并自动计算长度填入包头，最后拼接返回
        """
        # 1. 序列化数据区
        payload_bytes = self.payload.to_epdu()
        
        # 2. 自动更新包头中的长度字段 (数据区字节数)
        self.header.len = len(payload_bytes)
        
        # 3. 序列化包头
        header_bytes = self.header.pack()
        
        # 4. 拼接返回完整包 (头 + 数据)
        return header_bytes + payload_bytes

    @classmethod
    def unpack(cls, packet_bytes):
        """
        逆运算：将完整的二进制流拆解为头和数据区对象
        """
        if len(packet_bytes) < EpduHeader.HEADER_SIZE:
            raise ValueError(f"数据长度不足包头大小 ({EpduHeader.HEADER_SIZE} 字节)")
            
        # 1. 解包头部
        header = EpduHeader.unpack(packet_bytes[:EpduHeader.HEADER_SIZE])
        
        # 2. 提取对应长度的数据区
        payload_start = EpduHeader.HEADER_SIZE
        payload_end = payload_start + header.len
        
        if len(packet_bytes) < payload_end:
            raise ValueError(f"数据包长度异常：包头指示长度 {header.len}，但实际剩余长度只有 {len(packet_bytes) - payload_start}")
            
        payload_bytes = packet_bytes[payload_start:payload_end]
        
        # 3. 解包数据区
        payload = TargetData.from_epdu(payload_bytes)
        
        return cls(header, payload)

    @classmethod
    def from_hex_string(cls, hex_string):
        """
        从 16 进制字符串还原出完整包
        """
        hex_string_clean = hex_string.replace(' ', '')
        packet_bytes = bytes.fromhex(hex_string_clean)
        return cls.unpack(packet_bytes)

    def to_json_string(self):
        """
        将完整包以 JSON 字符串形式打印，方便调试
        """
        return json.dumps({
            "header": self.header.to_dict(),
            "payload": json.loads(self.payload.to_json_string())
        }, ensure_ascii=False, indent=4)
