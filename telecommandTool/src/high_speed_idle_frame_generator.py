#!/usr/bin/env python3
"""高速空闲USLP帧：VCID=63，1020字节，无PUS包，977字节PN填充。

按原低速实现优先：VCF为1字节、UPID=0、SCID默认FF01。
文档中的4字节VCF与1020/977字节长度矛盾，未采用。
"""
import argparse
from pathlib import Path
from high_speed_frame_generator import DATA_ZONE_SIZE, high_speed_profile
from uslp_common import format_hex, uint, wrap_packet


def pn_sequence(size: int = DATA_ZONE_SIZE) -> bytes:
    """D^0+D^1+D^2+D^22+D^32，全1初态，每帧重置，MSB先输出。"""
    uint('PN长度', size, 16)
    state = 0xFFFFFFFF
    output = bytearray()
    for _ in range(size):
        value = 0
        for _ in range(8):
            value = (value << 1) | ((state >> 31) & 1)
            feedback = ((state >> 31) ^ (state >> 21) ^ (state >> 1) ^ state) & 1
            state = ((state << 1) & 0xFFFFFFFF) | feedback
        output.append(value)
    return bytes(output)


def build_high_speed_idle_frame(*, scid: int = 0xFF01, vcf_count: int = 0) -> bytes:
    return wrap_packet(packet=pn_sequence(), scid=scid, vcf_count=vcf_count,
                       profile=high_speed_profile(vcid=63, map_id=0, idle=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    integer = lambda value: int(value, 0)
    parser.add_argument('--scid', type=integer, default=0xFF01)
    parser.add_argument('--vcf', type=integer, default=0)
    parser.add_argument('-o', '--output', type=Path)
    args = parser.parse_args()
    try:
        frame = build_high_speed_idle_frame(scid=args.scid, vcf_count=args.vcf)
    except ValueError as exc:
        parser.error(str(exc))
    if args.output:
        args.output.write_bytes(frame)
    print(f'高速空闲USLP帧：{len(frame)}字节')
    print(format_hex(frame))


if __name__ == '__main__':
    main()
