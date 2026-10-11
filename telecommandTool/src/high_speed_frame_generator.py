#!/usr/bin/env python3
"""生成单个1020字节高速USLP遥控帧，VCID默认10，可选10/5/4/63，TC(2,2)，不含CLTU。"""

import argparse
from pathlib import Path

from uslp_common import FrameProfile, build_pus_tc_packet, crc16_ccitt, format_hex, uint, wrap_packet

FRAME_SIZE = 1020
DATA_ZONE_SIZE = 977


def high_speed_profile(vcid: int = 10, map_id: int = 14, idle: bool = False) -> FrameProfile:
    return FrameProfile(vcid=vcid, map_id=map_id, security_header=b'\x5A' * 14,
                        security_trailer=b'\x5A' * 16, max_size=FRAME_SIZE,
                        construction_rule=1, upid=0, data_zone_size=DATA_ZONE_SIZE, idle=idle)


def build_high_speed_frame(*, app_data: bytes = b'',
                           scid: int = 0xFF01, vcf_count: int = 0, pid: int = 2,
                           pcat: int = 3, map_id: int = 14, sequence_count: int = 0,
                           sequence_flags: int = 3, vcid: int = 10) -> bytes:
    """单帧单包；用户提供当前分段，不自动拆文件或发送。"""
    for name, value, bits in (('PID', pid, 7), ('PCAT', pcat, 4),
                              ('包序列计数', sequence_count, 14), ('分段标志', sequence_flags, 2)):
        uint(name, value, bits)
    uint('VCID', vcid, 6)
    if vcid not in (10, 5, 4, 63):
        raise ValueError('高速VCID只能为10、5、4或63')
    if map_id not in (1, 14):
        raise ValueError('高速MAP ID只能为1（指令/注入）或14（大容量数据）')
    if not isinstance(app_data, bytes) or len(app_data) > DATA_ZONE_SIZE - 13:
        raise ValueError('高速应用数据必须为字节串，最长964字节')
    packet = build_pus_tc_packet(pid=pid, pcat=pcat, service_type=2, service_subtype=2,
                                 app_data=app_data,
                                 sequence_count=sequence_count)
    if sequence_flags != 3:
        body = packet[:2] + ((sequence_flags << 14) | sequence_count).to_bytes(2, 'big') + packet[4:-2]
        packet = body + crc16_ccitt(body).to_bytes(2, 'big')
    return wrap_packet(packet=packet, scid=scid, vcf_count=vcf_count,
                       profile=high_speed_profile(vcid=vcid, map_id=map_id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    integer = lambda value: int(value, 0)
    for name, default in [('scid', 0xFF01), ('vcf', 0), ('pid', 2), ('pcat', 3),
                          ('vcid', 10), ('map-id', 14), ('sequence-count', 0), ('sequence-flags', 3)]:
        parser.add_argument('--' + name, type=integer, default=default)
    parser.add_argument('--app-data', default='', help='完整应用数据HEX，原样组包，最多964字节')
    parser.add_argument('-o', '--output', type=Path)
    args = parser.parse_args()
    try:
        frame = build_high_speed_frame(scid=args.scid, vcf_count=args.vcf, pid=args.pid,
            pcat=args.pcat, map_id=args.map_id, vcid=args.vcid,
            sequence_count=args.sequence_count, sequence_flags=args.sequence_flags,
            app_data=bytes.fromhex(args.app_data))
    except ValueError as exc:
        parser.error(str(exc))
    if args.output:
        args.output.write_bytes(frame)
    print(f'高速USLP遥控帧：{len(frame)}字节')
    print(format_hex(frame))


if __name__ == '__main__':
    main()
