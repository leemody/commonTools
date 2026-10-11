#!/usr/bin/env python3
"""生成ST11时间调度低速USLP遥控帧。

共同输入：

| 字段 | 默认值 | 说明 |
|---|---|---|
| SCID | 0xFF01 | 直接写入帧主导头 |
| VCF | 0 | 虚拟信道帧计数 |
| PID / PCAT | 1 / 0x03 | 组成外层PUS包APID |

支持的TC：

| 命令 | PUS服务/子类型 | 应用数据 |
|---|---|---|
| enable | 11/1 | 0字节 |
| disable | 11/2 | 0字节 |
| reset | 11/3 | 0字节 |
| insert | 11/4 | 子调度表ID + N + N组（释放时间 + 完整TC请求包） |
| delete | 11/6 | 时间窗口 + N1 + N1个子调度表ID |
| shift | 11/8 | 时间偏移 + 时间窗口 + N1 + N1个子调度表ID |
| summary | 11/14 | 类型0 + N1 + N1个子调度表ID，N1不超过5 |

程序生成的共同字段：

| 字段 | 取值/算法 |
|---|---|
| 外层APID | `(PID << 4)`与PCAT按位或 |
| 内外层PUS包副导头源ID | 固定为`11111110110b`（0x07F6） |
| 外层包序列控制 | 0xC000（未分段、计数0） |
| 外层PUS版本/服务 | 0x20 / 0x0B |
| 外层包长、包ECF | 自动计算 |
| TFVN / 目的标志 | 12 / 1 |
| VCID / MAP ID | 5 / 0 |
| USLP控制字段 | 0x81（便捷、用户数据、无OCF、1字节VCF） |
| 安全头 / 安全尾 | 14个0x5A / 16个0x5A |
| TFDZ构造规则 / UPID | 111b / 00000b |
| 首导头/最后有效字节指针 | 0xFFFF，TFDZ内全部有效 |
| TFDF导头 | 0xE0 0xFF 0xFF |
| TFDZ | 一个完整外层PUS TC包 |
| 帧长、帧FECF | 自动计算 |

子调度表ID启用，调度组不启用，因此不编码组ID、N2或调度组ID。绝对时间为
从2020-01-01 00:00:00 UTC起算的4字节积秒。TM(11,13)是下行摘要报告，
不在本TC生成器中生成。

insert的每个--activity格式为：

    释放时间:PID:PCAT:服务类型:消息子类型:序列计数:应用数据HEX

命令行中的数值字段统一使用带0x前缀的十六进制；内层TC请求包的包长和ECF
由程序自动计算。

重复字段的传参规则：

| 协议重复项 | 命令行写法 | 程序生成的计数 |
|---|---|---|
| TC(11,4)的N条活动 | 每条活动分别写一个`--activity` | N等于`--activity`数量 |
| TC(11,6/8/14)的N1个子调度表 | 在一个`--sub-schedule-ids`后依次列出 | N1等于ID数量 |
| N2个调度组 | 本型号不启用，不提供参数 | 不编码N2和组ID |

不写`--sub-schedule-ids`表示N1=0，即不按子调度表限制。TC(11,14)的N1最大为5。

命令示例：

    python time_schedule_telecommand_frame_generator.py enable
    python time_schedule_telecommand_frame_generator.py disable --vcf 0x01
    python time_schedule_telecommand_frame_generator.py reset --vcf 0x02
    # 插入两条活动：重复写两次--activity，程序自动填写N=2
    python time_schedule_telecommand_frame_generator.py insert --sub-schedule-id 0x0001 --activity "0x0C845880:0x02:0x03:0x02:0x02:0x0000:50 01 01 02 03" --activity "0x0C8458BC:0x38:0x03:0x02:0x02:0x0001:50 01 AA 55"

    # 用两个子调度表过滤：程序自动填写N1=2
    python time_schedule_telecommand_frame_generator.py delete --time-type 0x01 --time-tag1 0x0C845880 --time-tag2 0x0C8458BC --sub-schedule-ids 0x0001 0x0002
    python time_schedule_telecommand_frame_generator.py shift --time-offset 0x00000078 --time-type 0x01 --time-tag1 0x0C845880 --time-tag2 0x0C8458BC --sub-schedule-ids 0x0001 0x0002
    python time_schedule_telecommand_frame_generator.py summary --sub-schedule-ids 0x0001 0x0002 --output summary.bin

所有多字节字段均按大端序编码；输出帧未加扰、未做信道编码且不含CLTU。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

CRC_INITIAL = 0xFFFF
CRC_POLYNOMIAL = 0x1021
PUS_SOURCE_ID = 0b11111110110
PUS_SCHEDULE = 0x0B
LOW_SPEED_VCID = 5
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


def build_pus_tc_packet(
    *,
    pid: int,
    pcat: int,
    service_type: int,
    service_subtype: int,
    app_data: bytes = b"",
    sequence_count: int = 0,
) -> bytes:
    for name, value, maximum in (
        ("PID", pid, 0x7F),
        ("PCAT", pcat, 0x0F),
        ("服务类型", service_type, 0xFF),
        ("消息子类型", service_subtype, 0xFF),
        ("包序列计数", sequence_count, 0x3FFF),
    ):
        if not 0 <= value <= maximum:
            raise ValueError(f"{name}应在0..0x{maximum:X}范围内")

    apid = (pid << 4) | pcat
    packet_without_ecf = b"".join(
        (
            (0x1800 | apid).to_bytes(2, "big"),
            (0xC000 | sequence_count).to_bytes(2, "big"),
            (5 + len(app_data) + 2 - 1).to_bytes(2, "big"),
            bytes((0x20, service_type, service_subtype)),
            PUS_SOURCE_ID.to_bytes(2, "big"),
            app_data,
        )
    )
    return packet_without_ecf + crc16_ccitt(packet_without_ecf).to_bytes(2, "big")


def wrap_low_speed_frame(*, scid: int, vcf_count: int, packet: bytes) -> bytes:
    if not 0 <= scid <= 0xFFFF:
        raise ValueError("SCID应在0..0xFFFF范围内")
    if not 0 <= vcf_count <= 0xFF:
        raise ValueError("VCF应在0..255范围内")
    if not 0 < len(packet) <= LOW_SPEED_PACKET_MAX_SIZE:
        raise ValueError(
            f"PUS包长{len(packet)}字节，应在1..{LOW_SPEED_PACKET_MAX_SIZE}字节范围内"
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
    return frame_without_fecf + crc16_ccitt(frame_without_fecf).to_bytes(2, "big")


def parse_integer(text: str) -> int:
    return int(text, 0)


def format_hex(data: bytes, width: int = 32) -> str:
    return "\n".join(
        " ".join(f"{value:02X}" for value in data[offset : offset + width])
        for offset in range(0, len(data), width)
    )


@dataclass(frozen=True)
class ScheduledActivity:
    release_time: int
    pid: int
    pcat: int
    service_type: int
    service_subtype: int
    app_data: bytes
    sequence_count: int = 0


def _uint(name: str, value: int, size: int) -> bytes:
    maximum = (1 << (size * 8)) - 1
    if not 0 <= value <= maximum:
        raise ValueError(f"{name}应在0..0x{maximum:X}范围内")
    return value.to_bytes(size, "big")


def _build_frame(
    subtype: int,
    app_data: bytes,
    *,
    scid: int,
    vcf_count: int,
    pid: int,
    pcat: int,
) -> bytes:
    packet = build_pus_tc_packet(
        pid=pid,
        pcat=pcat,
        service_type=PUS_SCHEDULE,
        service_subtype=subtype,
        app_data=app_data,
    )
    return wrap_low_speed_frame(scid=scid, vcf_count=vcf_count, packet=packet)


def build_enable_frame(*, scid: int = 0xFF01, vcf_count: int = 0,
                       pid: int = 1, pcat: int = 0x03) -> bytes:
    return _build_frame(1, b"", scid=scid, vcf_count=vcf_count, pid=pid, pcat=pcat)


def build_disable_frame(*, scid: int = 0xFF01, vcf_count: int = 0,
                        pid: int = 1, pcat: int = 0x03) -> bytes:
    return _build_frame(2, b"", scid=scid, vcf_count=vcf_count, pid=pid, pcat=pcat)


def build_reset_frame(*, scid: int = 0xFF01, vcf_count: int = 0,
                      pid: int = 1, pcat: int = 0x03) -> bytes:
    return _build_frame(3, b"", scid=scid, vcf_count=vcf_count, pid=pid, pcat=pcat)


def build_insert_frame(
    activities: list[ScheduledActivity],
    *,
    sub_schedule_id: int,
    scid: int = 0xFF01,
    vcf_count: int = 0,
    pid: int = 1,
    pcat: int = 0x03,
) -> bytes:
    if not 1 <= sub_schedule_id <= 0xFFFF:
        raise ValueError("地面使用的子调度表ID应在1..65535范围内")
    if not 1 <= len(activities) <= 0xFF:
        raise ValueError("活动数量应在1..255范围内")

    entries = []
    for activity in activities:
        request = build_pus_tc_packet(
            pid=activity.pid,
            pcat=activity.pcat,
            service_type=activity.service_type,
            service_subtype=activity.service_subtype,
            app_data=activity.app_data,
            sequence_count=activity.sequence_count,
        )
        entries.append(
            _uint("释放时间", activity.release_time, 4) + request
        )
    app_data = b"".join(
        (_uint("子调度表ID", sub_schedule_id, 2), bytes((len(activities),)), *entries)
    )
    return _build_frame(
        4, app_data, scid=scid, vcf_count=vcf_count, pid=pid, pcat=pcat
    )


def _schedule_filter(
    time_type: int,
    time_tag1: int | None,
    time_tag2: int | None,
    sub_schedule_ids: list[int],
) -> bytes:
    if time_type == 0:
        if time_tag1 is not None or time_tag2 is not None:
            raise ValueError("时间类型0不携带时间标签")
        time_fields = b""
    elif time_type == 1:
        if time_tag1 is None or time_tag2 is None:
            raise ValueError("时间类型1必须同时提供时间标签1和时间标签2")
        if time_tag1 > time_tag2:
            raise ValueError("时间标签1不能晚于时间标签2")
        time_fields = _uint("时间标签1", time_tag1, 4) + _uint("时间标签2", time_tag2, 4)
    elif time_type == 2:
        if time_tag1 is None or time_tag2 is not None:
            raise ValueError("时间类型2只提供时间标签1")
        time_fields = _uint("时间标签1", time_tag1, 4)
    elif time_type == 3:
        if time_tag1 is not None or time_tag2 is None:
            raise ValueError("时间类型3只提供时间标签2")
        time_fields = _uint("时间标签2", time_tag2, 4)
    else:
        raise ValueError("时间类型应在0..3范围内")

    if len(sub_schedule_ids) > 0xFF:
        raise ValueError("子调度表ID数量不能超过255")
    ids = b"".join(
        _uint("子调度表ID", value, 2)
        for value in sub_schedule_ids
        if value != 0
    )
    if len(ids) != len(sub_schedule_ids) * 2:
        raise ValueError("0号子调度表由飞行器内部占用，地面不得使用")
    return bytes((time_type,)) + time_fields + bytes((len(sub_schedule_ids),)) + ids


def build_delete_frame(
    *,
    time_type: int,
    time_tag1: int | None = None,
    time_tag2: int | None = None,
    sub_schedule_ids: list[int] | None = None,
    scid: int = 0xFF01,
    vcf_count: int = 0,
    pid: int = 1,
    pcat: int = 0x03,
) -> bytes:
    app_data = _schedule_filter(
        time_type, time_tag1, time_tag2, sub_schedule_ids or []
    )
    return _build_frame(
        6, app_data, scid=scid, vcf_count=vcf_count, pid=pid, pcat=pcat
    )


def build_shift_frame(
    *,
    time_offset: int,
    time_type: int,
    time_tag1: int | None = None,
    time_tag2: int | None = None,
    sub_schedule_ids: list[int] | None = None,
    scid: int = 0xFF01,
    vcf_count: int = 0,
    pid: int = 1,
    pcat: int = 0x03,
) -> bytes:
    app_data = _uint("时间偏移", time_offset, 4) + _schedule_filter(
        time_type, time_tag1, time_tag2, sub_schedule_ids or []
    )
    return _build_frame(
        8, app_data, scid=scid, vcf_count=vcf_count, pid=pid, pcat=pcat
    )


def build_summary_frame(
    *,
    sub_schedule_ids: list[int] | None = None,
    scid: int = 0xFF01,
    vcf_count: int = 0,
    pid: int = 1,
    pcat: int = 0x03,
) -> bytes:
    ids = sub_schedule_ids or []
    if len(ids) > 5:
        raise ValueError("TC(11,14)的子调度表ID数量不能超过5")
    app_data = _schedule_filter(0, None, None, ids)
    return _build_frame(
        14, app_data, scid=scid, vcf_count=vcf_count, pid=pid, pcat=pcat
    )


def _parse_activity(text: str) -> ScheduledActivity:
    try:
        release_time, pid, pcat, service, subtype, sequence, app_data = text.split(
            ":", 6
        )
        return ScheduledActivity(
            release_time=parse_integer(release_time),
            pid=parse_integer(pid),
            pcat=parse_integer(pcat),
            service_type=parse_integer(service),
            service_subtype=parse_integer(subtype),
            sequence_count=parse_integer(sequence),
            app_data=bytes.fromhex(app_data),
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "活动格式应为 RELEASE_TIME:PID:PCAT:SERVICE:SUBTYPE:SEQUENCE:APP_DATA_HEX"
        ) from error


def _common_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--scid", type=parse_integer, default=0xFF01,
                        help="帧SCID，默认0xFF01")
    common.add_argument("--vcf", type=parse_integer, default=0,
                        help="帧计数，默认0x00")
    common.add_argument("--pid", type=parse_integer, default=1,
                        help="外层PUS包PID，默认0x01")
    common.add_argument("--pcat", type=parse_integer, default=0x03,
                        help="外层PUS包PCAT，默认0x03")
    common.add_argument("-o", "--output", type=Path, help="可选：输出原始二进制帧")
    return common


def _add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--time-type", type=parse_integer, default=0,
                        help="时间窗口类型0x00..0x03，默认0x00")
    parser.add_argument("--time-tag1", type=parse_integer, help="可选：4字节时间标签1")
    parser.add_argument("--time-tag2", type=parse_integer, help="可选：4字节时间标签2")
    parser.add_argument(
        "--sub-schedule-ids", nargs="*", type=parse_integer, default=[], metavar="ID",
        help="N1个子调度表ID，例如：--sub-schedule-ids 0x0001 0x0002",
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    common = _common_parser()
    for name, help_text in (
        ("enable", "生成TC(11,1)启用帧"),
        ("disable", "生成TC(11,2)禁用帧"),
        ("reset", "生成TC(11,3)重置帧"),
    ):
        commands.add_parser(name, parents=[common], help=help_text)

    insert = commands.add_parser(
        "insert", parents=[common], help="生成TC(11,4)插入活动帧"
    )
    insert.add_argument("--sub-schedule-id", type=parse_integer, default=1,
                        help="子调度表ID，默认0x0001")
    insert.add_argument(
        "--activity", action="append", type=_parse_activity, required=True,
        metavar="RELEASE:PID:PCAT:SERVICE:SUBTYPE:SEQ:APP_HEX",
        help="一条活动；插入多条活动时重复使用此参数，N自动统计",
    )

    delete = commands.add_parser(
        "delete", parents=[common], help="生成TC(11,6)删除活动帧"
    )
    _add_filter_arguments(delete)

    shift = commands.add_parser(
        "shift", parents=[common], help="生成TC(11,8)时间转移帧"
    )
    shift.add_argument("--time-offset", type=parse_integer, default=0,
                       help="4字节相对时间，默认0x00000000")
    _add_filter_arguments(shift)

    summary = commands.add_parser(
        "summary", parents=[common], help="生成TC(11,14)摘要请求帧"
    )
    summary.add_argument(
        "--sub-schedule-ids", nargs="*", type=parse_integer, default=[], metavar="ID",
        help="最多5个子调度表ID，例如：--sub-schedule-ids 0x0001 0x0002",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    common = dict(scid=args.scid, vcf_count=args.vcf, pid=args.pid, pcat=args.pcat)
    try:
        if args.command == "enable":
            frame = build_enable_frame(**common)
        elif args.command == "disable":
            frame = build_disable_frame(**common)
        elif args.command == "reset":
            frame = build_reset_frame(**common)
        elif args.command == "insert":
            frame = build_insert_frame(
                args.activity, sub_schedule_id=args.sub_schedule_id, **common
            )
        elif args.command == "delete":
            frame = build_delete_frame(
                time_type=args.time_type,
                time_tag1=args.time_tag1,
                time_tag2=args.time_tag2,
                sub_schedule_ids=args.sub_schedule_ids,
                **common,
            )
        elif args.command == "shift":
            frame = build_shift_frame(
                time_offset=args.time_offset,
                time_type=args.time_type,
                time_tag1=args.time_tag1,
                time_tag2=args.time_tag2,
                sub_schedule_ids=args.sub_schedule_ids,
                **common,
            )
        else:
            frame = build_summary_frame(
                sub_schedule_ids=args.sub_schedule_ids, **common
            )
    except ValueError as error:
        raise SystemExit(f"参数错误：{error}") from error

    if args.output:
        args.output.write_bytes(frame)
    print(f"TC(11,{frame[33]})低速USLP遥控帧：{len(frame)}字节")
    print(format_hex(frame))


if __name__ == "__main__":
    main()
