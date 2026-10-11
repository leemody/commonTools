"""新增帧生成器共用的 USLP 编码工具；原有生成器保持独立。"""

from dataclasses import dataclass

from low_speed_telecommand_frame_generator import crc16_ccitt, format_hex
from time_schedule_telecommand_frame_generator import build_pus_tc_packet


def uint(name: str, value: int, bits: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < (1 << bits):
        raise ValueError(f"{name}应为0..{(1 << bits) - 1}范围内的整数")
    return value


@dataclass(frozen=True)
class FrameProfile:
    """当前完整包、1字节VCF帧结构的配置；其他结构需单独实现。"""

    vcid: int
    security_header: bytes
    security_trailer: bytes
    max_size: int = 510
    map_id: int = 0
    construction_rule: int = 7
    upid: int = 0
    data_zone_size: int = 0
    idle: bool = False


def wrap_packet(*, packet: bytes, scid: int, vcf_count: int, profile: FrameProfile) -> bytes:
    """封装完整PUS包，无插入区、无OCF；返回未加扰的原始帧。"""
    uint("SCID", scid, 16)
    uint("VCF", vcf_count, 8)
    uint("VCID", profile.vcid, 6)
    uint("MAP ID", profile.map_id, 4)
    uint("构造规则", profile.construction_rule, 3)
    uint("UPID", profile.upid, 5)
    if not packet:
        raise ValueError("PUS包不能为空")
    pointer = 0xFFFF
    if profile.data_zone_size:
        if len(packet) > profile.data_zone_size:
            raise ValueError(f"数据长度超过TFDZ上限{profile.data_zone_size}字节")
        if profile.idle and len(packet) != profile.data_zone_size:
            raise ValueError("空闲PN数据必须填满TFDZ")
        pointer = 0xFFFE if profile.idle else len(packet) - 1
        packet += b"\xAA" * (profile.data_zone_size - len(packet))
    tfdf_header = bytes(((profile.construction_rule << 5) | profile.upid,)) + pointer.to_bytes(2, "big")
    size = 8 + len(profile.security_header) + len(tfdf_header) + len(packet) + len(profile.security_trailer) + 2
    if size > profile.max_size or size > 65536:
        raise ValueError(f"帧长{size}字节，超过上限{min(profile.max_size, 65536)}字节")
    # MAP ID占4bit，最低位为主导头结束标志0；旧生成器MAP=0，输出不受影响。
    word = (12 << 28) | (scid << 12) | (1 << 11) | (profile.vcid << 5) | (profile.map_id << 1)
    data = b"".join((
        word.to_bytes(4, "big"), (size - 1).to_bytes(2, "big"),
        bytes((0x81, vcf_count)), profile.security_header, tfdf_header,
        packet, profile.security_trailer,
    ))
    return data + crc16_ccitt(data).to_bytes(2, "big")
