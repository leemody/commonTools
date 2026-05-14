import json
import struct

class TargetData:
    # 统一定义 EPDU 打包解包格式
    # < : 小端字节序
    # 3d: 3 个 8 字节 float (double)
    # 16s: 16 字节 bytes
    # 4d: 4 个 8 字节 float (double)
    # ? : 1 字节 bool
    PAYLOAD_FORMAT = '<3d 16s 4d ?'
    PAYLOAD_SIZE = struct.calcsize(PAYLOAD_FORMAT)

    # 指令单元头部格式
    # 根据描述：
    # 服务类型码 (1 byte)
    # 单元个数 (1 byte)
    # 单元类型码 (1 byte)
    # 设备号 (1 byte)
    # 长度H (1 byte) - 长度高字节
    # 长度L (1 byte) - 长度低字节
    # 为了方便，这里将服务类型码和单元个数作为前导
    # 将单元类型、设备号、长度(H+L)作为主体头部
    COMMAND_HEADER_FORMAT = '>BBBBH' # 服务类型(1), 单元个数(1), 单元类型(1), 设备号(1), 长度(2)
    COMMAND_HEADER_SIZE = struct.calcsize(COMMAND_HEADER_FORMAT)

    def __init__(self, target_coordinates, coordinate_system, duration, 
                 position_accuracy, velocity_accuracy, stay_duration, allow_continue,
                 service_type=0x50, unit_count=0x01, unit_type=0xF7, device_id=0x01):
        # 核心数据
        self.target_coordinates = target_coordinates
        self.coordinate_system = coordinate_system
        self.duration = duration
        self.position_accuracy = position_accuracy
        self.velocity_accuracy = velocity_accuracy
        self.stay_duration = stay_duration
        self.allow_continue = allow_continue
        # 指令头部数据
        self.service_type = service_type
        self.unit_count = unit_count
        self.unit_type = unit_type
        self.device_id = device_id

    @classmethod
    def from_json(cls, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(
            target_coordinates=data.get('target_coordinates', [0.0, 0.0, 0.0]),
            coordinate_system=data.get('coordinate_system', 'WGS84'),
            duration=data.get('duration', 0.0),
            position_accuracy=data.get('position_accuracy', 0.0),
            velocity_accuracy=data.get('velocity_accuracy', 0.0),
            stay_duration=data.get('stay_duration', 0.0),
            allow_continue=data.get('allow_continue', False),
            service_type=data.get('service_type', 0x50),
            unit_count=data.get('unit_count', 0x01),
            unit_type=data.get('unit_type', 0xF7),
            device_id=data.get('device_id', 0x01)
        )

    def to_json_string(self):
        d = self.__dict__.copy()
        return json.dumps(d, ensure_ascii=False, indent=4)

    def to_epdu(self):
        """
        将数据打包为 EPDU 数据区 (指令头 + 核心数据)
        """
        # 1. 打包核心数据 (Payload)
        coord_sys_bytes = self.coordinate_system.encode('utf-8').ljust(16, b'\0')[:16]
        payload_bytes = struct.pack(
            self.PAYLOAD_FORMAT,
            self.target_coordinates[0], self.target_coordinates[1], self.target_coordinates[2],
            coord_sys_bytes,
            self.duration, self.position_accuracy, self.velocity_accuracy,
            self.stay_duration, self.allow_continue
        )

        # 2. 计算指令单元长度 (从指令单元类型码开始到指令结束的字节长度)
        # 长度 = 单元类型码(1) + 设备号(1) + 长度(2) + 核心数据长度
        command_unit_len = 1 + 1 + 2 + len(payload_bytes)

        # 3. 打包指令头
        # 结构：服务类型码(1) + 单元个数(1) + 单元类型码(1) + 设备号(1) + 长度(2)
        command_header_bytes = struct.pack(
            self.COMMAND_HEADER_FORMAT,
            self.service_type,
            self.unit_count,
            self.unit_type,
            self.device_id,
            command_unit_len
        )

        # 4. 拼接指令头和核心数据
        return command_header_bytes + payload_bytes

    @classmethod
    def from_epdu(cls, epdu_bytes):
        """
        逆运算：将 EPDU 数据区字节流解析回 TargetData 对象
        """
        # 1. 解包指令头
        service_type, unit_count, unit_type, device_id, command_unit_len = struct.unpack_from(cls.COMMAND_HEADER_FORMAT, epdu_bytes)
        
        # 2. 提取核心数据
        payload_start = cls.COMMAND_HEADER_SIZE
        payload_bytes = epdu_bytes[payload_start:payload_start + cls.PAYLOAD_SIZE]
        
        # 3. 解包核心数据
        unpacked_payload = struct.unpack(cls.PAYLOAD_FORMAT, payload_bytes)
        
        target_coords = [unpacked_payload[0], unpacked_payload[1], unpacked_payload[2]]
        coordinate_system = unpacked_payload[3].rstrip(b'\0').decode('utf-8')
        
        return cls(
            target_coordinates=target_coords,
            coordinate_system=coordinate_system,
            duration=unpacked_payload[4],
            position_accuracy=unpacked_payload[5],
            velocity_accuracy=unpacked_payload[6],
            stay_duration=unpacked_payload[7],
            allow_continue=unpacked_payload[8],
            service_type=service_type,
            unit_count=unit_count,
            unit_type=unit_type,
            device_id=device_id
        )
