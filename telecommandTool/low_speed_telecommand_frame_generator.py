#!/usr/bin/env python3
"""生成单个低速USLP遥控帧。

调用方输入及默认值：

| 字段 | 范围/格式 | 默认值 | 用途 |
|---|---|---|---|
| SCID | 0..0xFFFF | 0xFF01 | 航天器标识，直接写入USLP帧主导头 |
| VCF | 0..255 | 0 | 虚拟信道帧计数 |
| PID | 0..127 | 2 | 与PCAT组成APID |
| PCAT | 0..15 | 0x03 | 与PID组成APID |
| 服务类型 | 0..255 | 0x02 | PUS TC服务类型 |
| 消息子类型 | 0..255 | 0x02 | PUS TC消息子类型 |
| 指令码 | 0..0xFFFF | 0x5001 | PUS应用数据开头的2字节指令码 |
| 参数 | 十六进制字节串 | 01 02 03 | 指令码之后的业务参数，可为空 |

程序生成：

| 字段 | 取值/算法 |
|---|---|
| APID | `(PID << 4)`与PCAT按位或 |
| PUS包副导头源ID | 固定为`11111110110b`（0x07F6） |
| PUS包序列控制 | 0xC000（未分段、计数0） |
| PUS包长度 | 根据指令码和参数长度计算 |
| PUS包ECF | CRC-16/CCITT-FALSE |
| TFVN / 目的标志 | 12 / 1 |
| VCID / MAP ID | 5 / 0 |
| USLP控制字段 | 0x81（便捷、用户数据、无OCF、1字节VCF） |
| 安全头 / 安全尾 | 14个0x5A / 16个0x5A |
| TFDZ构造规则 | `111b`：可变帧长的一个或多个完整MAPP |
| UPID | `00000b` |
| 首导头/最后有效字节指针 | `0xFFFF`：TFDZ内全部为有效数据 |
| TFDF导头 | 上述三项编码为`0xE0 0xFF 0xFF` |
| TFDZ | 一个完整PUS TC包 |
| USLP帧长度 | 43 + PUS包长度，最大510字节 |
| USLP帧FECF | CRC-16/CCITT-FALSE |

所有多字节字段均按大端序编码；输出为未加扰、未做信道编码且不含CLTU的帧。

命令示例：

    # 直接使用上述默认值
    python low_speed_telecommand_frame_generator.py

    # 指定全部字段，并将原始帧保存为frame.bin
    python low_speed_telecommand_frame_generator.py --scid 0xFF01 --vcf 0 --pid 2 --pcat 0x03 --service-type 0x02 --service-subtype 0x02 --command-code 0x5001 --parameters "01 02 03" --output frame.bin
"""

from __future__ import annotations

import argparse
from pathlib import Path


CRC_INITIAL = 0xFFFF
CRC_POLYNOMIAL = 0x1021
PUS_SOURCE_ID = 0b11111110110
LOW_SPEED_VCID = 5
LOW_SPEED_FRAME_MAX_SIZE = 510
LOW_SPEED_PACKET_MAX_SIZE = 467
TFDZ_CONSTRUCTION_RULE = 0b111
UPID = 0b00000
TFDZ_POINTER = 0xFFFF
TFDF_HEADER = bytes(((TFDZ_CONSTRUCTION_RULE << 5) | UPID,)) + TFDZ_POINTER.to_bytes(
    2, "big"
)


def crc16_ccitt(data: bytes) -> int:
    crc = CRC_INITIAL
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = (
                ((crc << 1) ^ CRC_POLYNOMIAL) if crc & 0x8000 else crc << 1
            ) & 0xFFFF
    return crc


def build_low_speed_frame(
    *,
    scid: int,
    vcf_count: int,
    pid: int,
    pcat: int,
    service_type: int,
    service_subtype: int,
    command_code: int,
    parameters: bytes = b"",
) -> bytes:
    """按调用方字段生成一个完整低速USLP遥控帧。"""
    for name, value, maximum in (
        ("SCID", scid, 0xFFFF),
        ("VCF", vcf_count, 0xFF),
        ("PID", pid, 0x7F),
        ("PCAT", pcat, 0x0F),
        ("服务类型", service_type, 0xFF),
        ("消息子类型", service_subtype, 0xFF),
        ("指令码", command_code, 0xFFFF),
    ):
        if not 0 <= value <= maximum:
            raise ValueError(f"{name}应在0..0x{maximum:X}范围内")

    apid = (pid << 4) | pcat
    app_data = command_code.to_bytes(2, "big") + parameters
    packet_without_ecf = b"".join(
        (
            (0x1800 | apid).to_bytes(2, "big"),
            b"\xC0\x00",
            (5 + len(app_data) + 2 - 1).to_bytes(2, "big"),
            bytes((0x20, service_type, service_subtype)),
            PUS_SOURCE_ID.to_bytes(2, "big"),
            app_data,
        )
    )
    packet = packet_without_ecf + crc16_ccitt(packet_without_ecf).to_bytes(2, "big")
    if len(packet) > LOW_SPEED_PACKET_MAX_SIZE:
        raise ValueError(
            f"PUS包长{len(packet)}字节，超过低速帧上限{LOW_SPEED_PACKET_MAX_SIZE}字节"
        )

    frame_size = 8 + 14 + 3 + len(packet) + 16 + 2
    first_word = (
        (0x0C << 28) | (scid << 12) | (1 << 11) | (LOW_SPEED_VCID << 5)
    )
    frame_without_fecf = b"".join(
        (
            first_word.to_bytes(4, "big"),
            (frame_size - 1).to_bytes(2, "big"),
            bytes((0x81, vcf_count)),
            bytes((0x5A,)) * 14,
            TFDF_HEADER,
            packet,
            bytes((0x5A,)) * 16,
        )
    )
    frame = frame_without_fecf + crc16_ccitt(frame_without_fecf).to_bytes(2, "big")
    if len(frame) > LOW_SPEED_FRAME_MAX_SIZE:
        raise ValueError(f"低速帧长{len(frame)}字节，超过上限{LOW_SPEED_FRAME_MAX_SIZE}字节")
    return frame


def parse_integer(text: str) -> int:
    """接受十进制或带0x前缀的十六进制整数。"""
    return int(text, 0)


def format_hex(data: bytes, width: int = 32) -> str:
    return "\n".join(
        " ".join(f"{value:02X}" for value in data[offset : offset + width])
        for offset in range(0, len(data), width)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scid", type=parse_integer, default=0xFF01)
    parser.add_argument("--vcf", type=parse_integer, default=0)
    parser.add_argument("--pid", type=parse_integer, default=2)
    parser.add_argument("--pcat", type=parse_integer, default=0x03)
    parser.add_argument("--service-type", type=parse_integer, default=0x02)
    parser.add_argument("--service-subtype", type=parse_integer, default=0x02)
    parser.add_argument("--command-code", type=parse_integer, default=0x5001)
    parser.add_argument(
        "--parameters", default="01 02 03", help="参数十六进制字节串，可含空格"
    )
    parser.add_argument("-o", "--output", type=Path, help="可选：输出原始二进制帧")
    args = parser.parse_args()

    try:
        parameters = bytes.fromhex(args.parameters)
        frame = build_low_speed_frame(
            scid=args.scid,
            vcf_count=args.vcf,
            pid=args.pid,
            pcat=args.pcat,
            service_type=args.service_type,
            service_subtype=args.service_subtype,
            command_code=args.command_code,
            parameters=parameters,
        )
    except ValueError as error:
        parser.error(str(error))

    if args.output:
        args.output.write_bytes(frame)
    print(f"低速USLP遥控帧：{len(frame)}字节")
    print(format_hex(frame))


if __name__ == "__main__":
    main()
