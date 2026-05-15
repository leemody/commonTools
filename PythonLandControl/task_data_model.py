import struct
from dataclasses import dataclass
from typing import List, Tuple


FRAME_HEADER = b"\x00\x00\x00\x00\x00"
DEFAULT_APID = 0x43
DEFAULT_SEQUENCE_FLAGS = 0x3
DEFAULT_SEQUENCE_COUNT = 0


def _check_range(name: str, value: int, minimum: int, maximum: int) -> None:
    if value < minimum or value > maximum:
        raise ValueError(f"{name} out of range: {value}, expected {minimum}..{maximum}")


@dataclass
class Step:
    """
    TaskPlan Step:
        device_id(1) + cmd_id(2, BE) + arg_len(2, BE) + args
    """

    device_id: int = 0
    cmd_id: int = 0
    args: bytes = b""

    HEADER_FORMAT = ">BHH"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    @property
    def arg_len(self) -> int:
        return len(self.args)

    def to_bytes(self) -> bytes:
        _check_range("device_id", self.device_id, 0, 0xFF)
        _check_range("cmd_id", self.cmd_id, 0, 0xFFFF)
        _check_range("arg_len", self.arg_len, 0, 0xFFFF)
        return struct.pack(self.HEADER_FORMAT, self.device_id, self.cmd_id, self.arg_len) + self.args

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0) -> Tuple["Step", int]:
        if offset + cls.HEADER_SIZE > len(data):
            raise ValueError("not enough bytes for Step header")

        device_id, cmd_id, arg_len = struct.unpack_from(cls.HEADER_FORMAT, data, offset)
        args_start = offset + cls.HEADER_SIZE
        args_end = args_start + arg_len

        if args_end > len(data):
            raise ValueError("not enough bytes for Step args")

        return cls(device_id=device_id, cmd_id=cmd_id, args=data[args_start:args_end]), cls.HEADER_SIZE + arg_len

    def __repr__(self) -> str:
        return f"Step(device_id=0x{self.device_id:02X}, cmd_id=0x{self.cmd_id:04X}, arg_len={self.arg_len})"


class TaskPlanData:
    """
    TaskPlanData:
        format_ver(1) + plan_id(2, BE) + step_count(1) + steps[]
    """

    HEADER_FORMAT = ">BHB"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    def __init__(self, format_ver: int = 1, plan_id: int = 100, steps: List[Step] = None):
        self.format_ver = format_ver
        self.plan_id = plan_id
        self.steps = steps if steps is not None else []

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def to_bytes(self) -> bytes:
        _check_range("format_ver", self.format_ver, 0, 0xFF)
        _check_range("plan_id", self.plan_id, 0, 0xFFFF)
        _check_range("step_count", self.step_count, 0, 0xFF)

        header = struct.pack(self.HEADER_FORMAT, self.format_ver, self.plan_id, self.step_count)
        return header + b"".join(step.to_bytes() for step in self.steps)

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0) -> Tuple["TaskPlanData", int]:
        if offset + cls.HEADER_SIZE > len(data):
            raise ValueError("not enough bytes for TaskPlanData header")

        format_ver, plan_id, step_count = struct.unpack_from(cls.HEADER_FORMAT, data, offset)
        current = offset + cls.HEADER_SIZE
        steps: List[Step] = []

        for _ in range(step_count):
            step, step_size = Step.from_bytes(data, current)
            steps.append(step)
            current += step_size

        return cls(format_ver=format_ver, plan_id=plan_id, steps=steps), current - offset

    def add_step(self, device_id: int, cmd_id: int, args: bytes = b"") -> None:
        self.steps.append(Step(device_id=device_id, cmd_id=cmd_id, args=args))

    def __repr__(self) -> str:
        return f"TaskPlanData(format_ver={self.format_ver}, plan_id={self.plan_id}, step_count={self.step_count}, steps={self.steps})"


def pack_epdu_primary_header(payload_len: int,
                             apid: int = DEFAULT_APID,
                             sequence_flags: int = DEFAULT_SEQUENCE_FLAGS,
                             sequence_count: int = DEFAULT_SEQUENCE_COUNT) -> bytes:
    """
    Pack a 6-byte CCSDS/EPDU primary header in big-endian order.
    payload_len is the TaskPlan data length; the header length field is payload_len - 1.
    """
    _check_range("apid", apid, 0, 0x07FF)
    _check_range("sequence_flags", sequence_flags, 0, 0x03)
    _check_range("sequence_count", sequence_count, 0, 0x3FFF)

    if payload_len <= 0:
        raise ValueError("payload_len must be positive")

    length_field = payload_len - 1
    _check_range("packet_data_length", length_field, 0, 0xFFFF)

    word1 = (1 << 12) | apid
    word2 = (sequence_flags << 14) | sequence_count
    return struct.pack(">HHH", word1, word2, length_field)


def build_tc_frame(task_plan_data: TaskPlanData,
                   apid: int = DEFAULT_APID,
                   sequence_count: int = DEFAULT_SEQUENCE_COUNT,
                   frame_header: bytes = FRAME_HEADER) -> bytes:
    if len(frame_header) != 5:
        raise ValueError("frame_header must be exactly 5 bytes")

    payload = task_plan_data.to_bytes()
    epdu_header = pack_epdu_primary_header(payload_len=len(payload),
                                           apid=apid,
                                           sequence_count=sequence_count)
    return frame_header + epdu_header + payload


def format_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)
