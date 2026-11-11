#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上注包校验工具
================
校验 962 字节帧格式的上注包：
  1. 逐帧检查帧序号是否从 0 连续递增
  2. 逐帧检查有效数据长度字段（满帧 958，末帧为实际值）
  3. 检查末帧 0x55 填充
  4. 去掉帧头和填充后还原数据，与源文件做哈希比对

用法：
    python verify_uplink_pkg.py <源文件> <上注包文件>
"""

import argparse
import hashlib
import struct
import sys

FRAME_PAYLOAD = 958
FRAME_SIZE = 962
PAD_BYTE = 0x55


def verify(source: str, package: str) -> bool:
    src = open(source, "rb").read()
    pkg = open(package, "rb").read()

    if len(pkg) % FRAME_SIZE != 0:
        print(f"[失败] 上注包大小 {len(pkg)} 不是 962 的整数倍")
        return False

    n = len(pkg) // FRAME_SIZE
    seq_ok = len_ok = pad_ok = True
    restored = bytearray()

    for i in range(n):
        frame = pkg[i * FRAME_SIZE:(i + 1) * FRAME_SIZE]
        seq, vlen = struct.unpack(">HH", frame[:4])
        payload = frame[4:]
        if seq != i % 65536:
            seq_ok = False
            print(f"[失败] 第 {i} 帧序号为 {seq}，期望 {i % 65536}")
        if not (1 <= vlen <= FRAME_PAYLOAD):
            len_ok = False
            print(f"[失败] 第 {i} 帧长度字段 {vlen} 越界")
        restored += payload[:vlen]
        if vlen < FRAME_PAYLOAD:
            if i != n - 1:
                len_ok = False
                print(f"[失败] 第 {i} 帧（非末帧）长度 {vlen} < 958")
            if any(b != PAD_BYTE for b in payload[vlen:]):
                pad_ok = False
                print(f"[失败] 末帧填充字节不是 0x55")

    src_hash = hashlib.md5(src).hexdigest()
    rst_hash = hashlib.md5(bytes(restored)).hexdigest()
    size_ok = len(src) == len(restored)

    print("=" * 56)
    print(f"上注包     : {package}")
    print(f"总帧数     : {n}")
    print(f"序号连续   : {'通过' if seq_ok else '失败'}")
    print(f"长度字段   : {'通过' if len_ok else '失败'}")
    print(f"0x55 填充  : {'通过' if pad_ok else '失败'}")
    print(f"源文件大小 : {len(src)}  还原大小: {len(restored)}  {'一致' if size_ok else '不一致!'}")
    print(f"源文件 MD5 : {src_hash}")
    print(f"还原 MD5   : {rst_hash}")
    print(f"还原比对   : {'通过' if src_hash == rst_hash else '失败'}")
    print("=" * 56)
    return seq_ok and len_ok and pad_ok and size_ok and src_hash == rst_hash


def main():
    parser = argparse.ArgumentParser(description="上注包校验工具")
    parser.add_argument("source", help="源文件")
    parser.add_argument("package", help="上注包文件")
    args = parser.parse_args()
    ok = verify(args.source, args.package)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
