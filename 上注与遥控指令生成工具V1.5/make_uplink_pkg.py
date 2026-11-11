#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上注包生成工具
================
将任意二进制文件按固定帧长切分为上注包。

帧格式（每帧 962 字节）：
    [2 字节帧序号][2 字节有效数据长度][958 字节有效数据区]
  - 帧序号：从 0 开始递增（可用 --start-seq 修改起始值）
  - 有效数据长度：本帧实际有效数据字节数（满帧为 958，末帧为实际剩余字节数）
  - 末帧有效数据不足 958 字节时，用 0x55 填充至 958 字节

用法：
    python make_uplink_pkg.py <输入文件> [-o <输出文件>] [--start-seq N] [--endian big|little]

示例：
    python make_uplink_pkg.py design_top.bin
    python make_uplink_pkg.py storage_udp_app -o storage_udp_app_uplink.bin
"""

import argparse
import os
import struct
import sys

FRAME_PAYLOAD_SIZE = 958      # 每帧有效数据区大小
FRAME_SIZE = 2 + 2 + FRAME_PAYLOAD_SIZE  # 每帧总长 962 字节
PAD_BYTE = 0x55               # 末帧填充字节


def make_uplink_package(input_path: str, output_path: str,
                        start_seq: int = 0, endian: str = "big") -> dict:
    """将输入文件切分为上注包并写入输出文件，返回统计信息。"""
    fmt = ">H" if endian == "big" else "<H"
    total_frames = 0
    file_size = os.path.getsize(input_path)

    with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
        seq = start_seq
        while True:
            chunk = fin.read(FRAME_PAYLOAD_SIZE)
            if not chunk:
                break
            valid_len = len(chunk)
            if valid_len < FRAME_PAYLOAD_SIZE:
                chunk = chunk + bytes([PAD_BYTE]) * (FRAME_PAYLOAD_SIZE - valid_len)
            fout.write(struct.pack(fmt, seq & 0xFFFF))
            fout.write(struct.pack(fmt, valid_len))
            fout.write(chunk)
            total_frames += 1
            seq = (seq + 1) & 0xFFFF

    return {
        "input": input_path,
        "output": output_path,
        "input_size": file_size,
        "frames": total_frames,
        "output_size": total_frames * FRAME_SIZE,
        "last_valid_len": (file_size % FRAME_PAYLOAD_SIZE) or FRAME_PAYLOAD_SIZE,
    }


def main():
    parser = argparse.ArgumentParser(description="上注包生成工具（962 字节/帧）")
    parser.add_argument("input", help="输入二进制文件")
    parser.add_argument("-o", "--output", help="输出上注包文件（默认 <输入名>_uplink.bin）")
    parser.add_argument("--start-seq", type=lambda x: int(x, 0), default=0,
                        help="起始帧序号（默认 0）")
    parser.add_argument("--endian", choices=["big", "little"], default="big",
                        help="序号/长度字段的字节序（默认 big 大端）")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"错误：输入文件不存在：{args.input}", file=sys.stderr)
        sys.exit(1)

    output = args.output or (os.path.splitext(args.input)[0] + "_uplink.bin")
    info = make_uplink_package(args.input, output, args.start_seq, args.endian)

    print("=" * 56)
    print("上注包生成完成")
    print(f"  输入文件     : {info['input']} ({info['input_size']} 字节)")
    print(f"  输出文件     : {info['output']} ({info['output_size']} 字节)")
    print(f"  总帧数       : {info['frames']}")
    print(f"  帧格式       : 2B 序号 + 2B 长度 + 958B 数据 (共 962B/帧)")
    print(f"  末帧有效长度 : {info['last_valid_len']} 字节（不足部分已填充 0x55）")
    print(f"  字节序       : {args.endian}")
    print("=" * 56)


if __name__ == "__main__":
    main()
