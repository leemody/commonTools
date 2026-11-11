"""批量生成在轨编程上注高速帧，避免前端逐帧请求后端。"""

import binascii
from typing import Optional

import high_speed_frame_generator as high
from time_schedule_telecommand_frame_generator import PUS_SOURCE_ID

MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_FRAME_COUNT = 100_000
CRC_INITIAL = 0xFFFF


def _build_high_speed_frame_fast(
    *,
    app_data: bytes,
    scid: int,
    vcf_count: int,
    pid: int,
    pcat: int,
    vcid: int,
    map_id: int,
    sequence_count: int,
    sequence_flags: int,
) -> bytes:
    """和标准高速生成器使用相同布局，仅将CRC计算交给C实现。"""
    if sequence_flags == 3:
        sequence_count = 0
    for name, value, bits in (("SCID", scid, 16), ("VCF", vcf_count, 8),
                              ("PID", pid, 7), ("PCAT", pcat, 4),
                              ("MAP ID", map_id, 4), ("VCID", vcid, 6),
                              ("包序列计数", sequence_count, 14),
                              ("分段标志", sequence_flags, 2)):
        high.uint(name, value, bits)
    if vcid not in (10, 5, 4, 63):
        raise ValueError("高速VCID只能为10、5、4或63")
    if map_id not in (1, 14):
        raise ValueError("高速MAP ID只能为1（指令/注入）或14（大容量数据）")
    if not isinstance(app_data, bytes) or len(app_data) > high.DATA_ZONE_SIZE - 13:
        raise ValueError("高速应用数据必须为字节串，最长964字节")

    apid = (pid << 4) | pcat
    packet_without_ecf = b"".join((
        (0x1800 | apid).to_bytes(2, "big"),
        (0xC000 | sequence_count).to_bytes(2, "big"),
        (len(app_data) + 6).to_bytes(2, "big"),
        bytes((0x20, 2, 2)),
        PUS_SOURCE_ID.to_bytes(2, "big"),
        app_data,
    ))
    packet = packet_without_ecf + binascii.crc_hqx(packet_without_ecf, CRC_INITIAL).to_bytes(2, "big")
    if sequence_flags != 3:
        body = packet[:2] + ((sequence_flags << 14) | sequence_count).to_bytes(2, "big") + packet[4:-2]
        packet = body + binascii.crc_hqx(body, CRC_INITIAL).to_bytes(2, "big")

    packet_length = high.DATA_ZONE_SIZE
    if len(packet) > packet_length:
        raise ValueError(f"数据长度超过TFDZ上限{packet_length}字节")
    tfdf_header = bytes((0x20,)) + (len(packet) - 1).to_bytes(2, "big")
    tfdz = packet + b"\xAA" * (packet_length - len(packet))
    size = high.FRAME_SIZE
    word = (12 << 28) | (scid << 12) | (1 << 11) | (vcid << 5) | (map_id << 1)
    frame_without_fecf = b"".join((
        word.to_bytes(4, "big"), (size - 1).to_bytes(2, "big"),
        bytes((0x81, vcf_count)), b"\x5A" * 14, tfdf_header, tfdz, b"\x5A" * 16,
    ))
    return frame_without_fecf + binascii.crc_hqx(frame_without_fecf, CRC_INITIAL).to_bytes(2, "big")


def build_orbit_programming_frames(
    data: bytes,
    *,
    scid: int = 0xFF01,
    vcf_count: int = 0,
    pid: int = 2,
    pcat: int = 3,
    vcid: int = 10,
    map_id: int = 14,
    sequence_count: int = 0,
    sequence_flags: int = 3,
    add_422: bool = False,
    line_length_enabled: bool = True,
    line_length: Optional[int] = 962,
) -> bytearray:
    """生成连续的1020字节帧；所有帧保留相同VCF，尾行按配置补AA。"""
    if not isinstance(data, bytes):
        raise ValueError("上注文件内容必须是字节数据")
    if not isinstance(add_422, bool) or not isinstance(line_length_enabled, bool):
        raise ValueError("422和每行长度开关必须是布尔值")

    max_file_bytes = 956 if add_422 else 962
    if line_length_enabled:
        if isinstance(line_length, bool) or not isinstance(line_length, int):
            raise ValueError("每行读取字节长度必须是整数")
        if not 1 <= line_length <= max_file_bytes:
            raise ValueError(f"每行读取字节长度须为1至{max_file_bytes}字节")
        chunk_size = line_length
    else:
        chunk_size = max_file_bytes

    frame_count = max(1, (len(data) + chunk_size - 1) // chunk_size)
    if frame_count > MAX_FRAME_COUNT:
        raise ValueError(f"拆分后帧数不能超过{MAX_FRAME_COUNT}")

    output = bytearray()
    for index in range(frame_count):
        offset = index * chunk_size
        part = data[offset:offset + chunk_size]
        if line_length_enabled and len(part) < chunk_size:
            part = part.ljust(chunk_size, b"\xAA")

        if add_422:
            length = len(part)
            app_data = bytearray((0x5F, 0x01, 0xEB, 0x90, 0x0F))
            app_data.extend(length.to_bytes(2, "big"))
            app_data.extend(part)
            app_data.append(sum(app_data[4:]) & 0xFF)
        else:
            app_data = bytearray((0x5F, 0x01))
            app_data.extend(part)

        independent = sequence_flags == 3
        if independent or frame_count == 1:
            frame_flags = 3
        elif index == 0:
            frame_flags = 1
        elif index == frame_count - 1:
            frame_flags = 2
        else:
            frame_flags = 0
        packet_sequence_count = 0 if independent else (sequence_count + index) & 0x3FFF

        output.extend(_build_high_speed_frame_fast(
            app_data=bytes(app_data),
            scid=scid,
            vcf_count=vcf_count,
            pid=pid,
            pcat=pcat,
            vcid=vcid,
            map_id=map_id,
            sequence_count=packet_sequence_count,
            sequence_flags=frame_flags,
        ))

    return output