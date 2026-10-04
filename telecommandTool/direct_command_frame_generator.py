#!/usr/bin/env python3
"""生成直接指令USLP帧：VCID=4，TC(2,1)，两组同步字和9字节指令码。

其余沿用低速帧：安全头6个5A、安全尾16个5A、无插入区和OCF，最大510字节。
24字节应用数据 = (2C 79 5E + 9字节指令码) * 2；完整PUS包37字节、帧72字节。
源ID固定0x07F6；PID/PCAT默认2/3，可按实际指令目标设置。
"""

import argparse
from pathlib import Path

from uslp_common import FrameProfile, build_pus_tc_packet, format_hex, uint, wrap_packet


SYNC_WORD = bytes.fromhex("2C 79 5E")
DIRECT_PROFILE = FrameProfile(vcid=4, security_header=b"\x5A" * 6, security_trailer=b"\x5A" * 16)


def build_direct_command_frame(*, command_code: bytes,
                               scid: int = 0xFF01, vcf_count: int = 0,
                               pid: int = 2, pcat: int = 3) -> bytes:
    """输入一份9字节指令码，连同同步字自动重复两次，不截断、不填充。"""
    if not isinstance(command_code, bytes) or len(command_code) != 9:
        raise ValueError("遥控指令码必须恰好为9字节")
    uint("PID", pid, 7)
    uint("PCAT", pcat, 4)
    packet = build_pus_tc_packet(
        pid=pid, pcat=pcat, service_type=2, service_subtype=1,
        app_data=(SYNC_WORD + command_code) * 2,
    )
    return wrap_packet(packet=packet, scid=scid, vcf_count=vcf_count, profile=DIRECT_PROFILE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    integer = lambda value: int(value, 0)
    parser.add_argument("--scid", type=integer, default=0xFF01)
    parser.add_argument("--vcf", type=integer, default=0)
    parser.add_argument("--pid", type=integer, default=2)
    parser.add_argument("--pcat", type=integer, default=3)
    parser.add_argument("--command-code", required=True, help="9字节指令码HEX，不含同步字，自动重复两次")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    try:
        frame = build_direct_command_frame(
            command_code=bytes.fromhex(args.command_code),
            scid=args.scid, vcf_count=args.vcf, pid=args.pid, pcat=args.pcat,
        )
    except ValueError as error:
        parser.error(str(error))
    if args.output:
        args.output.write_bytes(frame)
    print(f"直接指令USLP帧：{len(frame)}字节")
    print(format_hex(frame))


if __name__ == "__main__":
    main()
