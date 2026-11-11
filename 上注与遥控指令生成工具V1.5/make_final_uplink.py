#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终上注数据生成程序（依据《固存与机械臂控制模块硬件使用说明 V1.9》8.5.2 节 表 8-6）
======================================================================================

TFDF 帧结构（数据区长度 N 可配置，默认 958，共 N+28 字节/帧）：

  +------+------+----------+--------------+----------------+----------+
  | 0xEB | 0x90 | 指令码    | 有效数据长度  | TFDF（N+22 字节）          | 累加和 |
  | 1B   | 1B   | 1B       | 2B           |                            | 1B    |
  +------+------+----------+--------------+----------------+----------+
  有效数据长度 = TFDF 帧长度 = N+22

  TFDF（N+22B） = TFDF 导头 3B + TFDZ（N+19B）
  TFDZ（N+19B） = TFDZ 导头 11B + PUS TC 消息（N+6B） + 包差错控制 2B
  PUS TC（N+6B）= 0x5F01 (2B) + 数据域（N+4B）
  数据域（N+4B）= 序号 2B + 有效数据长度 2B + 数据 N 字节
                 （末帧数据不足 N 时填 0x55，长度字段记录实际有效字节数）
  累加和        = 帧内「指令码 … 包差错控制」全部字节之和的低 8 位

输出级别（--level，六选一）：
  frame   完整上注帧（EB90 + 指令码 + 长度 + TFDF + 累加和，N+28 字节）
  tfdf    TFDF 帧（TFDF导头 + TFDZ + 包差错控制，N+22 字节）
  tfdz    TFDZ（TFDZ导头 + PUS TC 消息 + 包差错控制，N+19 字节）
  pus     PUS TC 消息（5F01 + 数据域，N+6 字节）
  domain  数据域（序号 + 长度 + 数据，N+4 字节）
  all     同时输出 frame / tfdf / tfdz / pus / domain 五种包（5 个文件，文件名带包长）

包差错控制（--ecc）：
  crc16-pus   （默认）USLP（CCSDS 732.1-B-2）CRC-16 循环冗余编码：
              G(X)=X16+X12+X5+1，移位寄存器预置全"1"，模 2 运算，
              等价于 CRC-16/CCITT-FALSE（poly=0x1021, init=0xFFFF, 无反射, 无终异或）；
              覆盖范围 = 仅 PUS TC 消息（5F01 + 序号 + 长度 + 数据，N+6 字节）
  crc16       同上算法，但覆盖 TFDF 帧除差错控制域外的全部字节
              （TFDF 导头 3B + TFDZ 导头 11B + PUS TC 消息，共 N+20 字节）——USLP 规程方式
  zeros       填 0x0000
  sum16       16 位累加和

文档未定义、由参数控制的字段（默认值见下）：
  --tfdf-hdr    TFDF 导头 3 字节，默认 00 00 00
  --tfdz-hdr    TFDZ 导头 11 字节，默认全 00
  --pus-id      PUS TC 消息标识，默认 5F01
  --data-len    数据区长度 N，默认 958（此时整帧 986 字节）
  --type-code   指令码：0x0E 处理器上注（默认）/ 0x1E 高速 Ku 上注
  --start-seq   数据域序号起始值，默认 1
  --seq-endian / --len-endian  序号与长度字段字节序，默认 big

用法示例：
  python make_final_uplink.py design_top.bin --type-code 0x0E -o design_top_uplink986.bin
  python make_final_uplink.py storage_udp_app --type-code 0x1E -o storage_udp_app_uplink986.bin
  python make_final_uplink.py storage_udp_app --level all -o out.bin        # 输出五种包
      # → out_frame986.bin / out_tfdf980.bin / out_tfdz977.bin / out_pus964.bin / out_data962.bin
  python make_final_uplink.py xxx.bin --data-len 512 --ecc crc16 --level tfdf
  python make_final_uplink.py --verify design_top_uplink986.bin             # 仅校验（自动识别级别）
"""

import argparse
import os
import struct
import sys

# ----------------------------- 帧格式常量（N=958 时的默认尺寸） -----------------------------
SYNC = b"\xEB\x90"          # 帧同步头
PAYLOAD_SIZE = 958          # 默认数据区长度 N
DATA_DOMAIN_SIZE = 2 + 2 + PAYLOAD_SIZE      # 962 = 序号 + 长度 + 数据
PUS_SIZE = 2 + DATA_DOMAIN_SIZE              # 964 = 0x5F01 + 数据域
TFDZ_SIZE = 11 + PUS_SIZE + 2                # 977 = 导头 + PUS + 包差错控制
TFDF_SIZE = 3 + TFDZ_SIZE                    # 980 = TFDF导头 + TFDZ
FRAME_SIZE = 2 + 1 + 2 + TFDF_SIZE + 1       # 986 = EB90 + 指令码 + 长度 + TFDF + 累加和
PAD_BYTE = 0x55             # 末帧填充字节
TFDZ_HDR_LEN = 11
TFDF_HDR_LEN = 3

# 帧内偏移（0-based，与 N 无关）：同步头2 + 指令码1 + 长度2 → TFDF导头3 → TFDZ导头11 → 0x5F01 2 → 数据域
DATA_DOMAIN_OFFSET = 2 + 1 + 2 + TFDF_HDR_LEN + TFDZ_HDR_LEN + 2      # = 21
PAYLOAD_OFFSET = DATA_DOMAIN_OFFSET + 4                                # = 25

LEVELS = ("frame", "tfdf", "tfdz", "pus", "domain", "all")
ALL_LEVELS = ("frame", "tfdf", "tfdz", "pus", "domain")
# 文件名中的级别标记（domain 用 data，避免与目录名混淆）
LEVEL_TAG = {"frame": "frame", "tfdf": "tfdf", "tfdz": "tfdz", "pus": "pus", "domain": "data"}
LEVEL_NAME = {
    "frame": "完整上注帧",
    "tfdf": "TFDF 帧",
    "tfdz": "TFDZ",
    "pus": "PUS TC 消息",
    "domain": "数据域",
    "all": "全部五种（frame/tfdf/tfdz/pus/domain）",
}
# 向后兼容：不含包长的固定后缀表（旧引用仍可用）
LEVEL_SUFFIX = {lv: "_" + LEVEL_TAG[lv] for lv in ALL_LEVELS}


def sizes(data_len: int = PAYLOAD_SIZE) -> dict:
    """各级别包尺寸（字节）。"""
    return {
        "domain": data_len + 4,    # 序号2 + 长度2 + 数据N
        "pus": data_len + 6,       # 5F01 + 数据域
        "tfdz": data_len + 19,     # 导头11 + PUS + 差错控制2
        "tfdf": data_len + 22,     # TFDF导头3 + TFDZ
        "frame": data_len + 28,    # EB90 + 指令码 + 长度 + TFDF + 累加和
    }


def level_filename(output_path: str, level: str, data_len: int) -> str:
    """按级别生成带包长的输出文件名，如 design_top_frame986.bin / design_top_tfdf980.bin。"""
    root, ext = os.path.splitext(output_path)
    return f"{root}_{LEVEL_TAG[level]}{sizes(data_len)[level]}{ext or '.bin'}"


# ----------------------------- CRC-16（USLP CCSDS 732.1-B-2） -----------------------------
def _crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE：poly=0x1021, init=0xFFFF（预置全"1"）, 无反射, 无终异或。

    与 USLP（CCSDS 732.1-B-2）帧差错控制规程一致：
      CRCW = [X16·M(X) ⊕ X(n-16)·L(X)] mod G(X)，G(X) = X16+X12+X5+1，模 2 运算。
    """
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


ECC_MODES = ("crc16", "crc16-pus", "zeros", "sum16")


def make_ecc(data: bytes, mode: str, endian: str) -> bytes:
    """计算包差错控制 2 字节。data 为其覆盖范围的数据。"""
    fmt = ">H" if endian == "big" else "<H"
    if mode == "zeros":
        return b"\x00\x00"
    if mode in ("crc16", "crc16-pus", "ccitt"):
        return struct.pack(fmt, _crc16_ccitt_false(data))
    if mode == "sum16":
        return struct.pack(fmt, sum(data) & 0xFFFF)
    raise ValueError(f"未知 ecc 模式: {mode}")


def parse_hex_bytes(text: str, expect_len: int, name: str) -> bytes:
    """解析 "00 00 00" / "000000" 形式的十六进制串。"""
    cleaned = text.replace("0x", "").replace(" ", "").replace(",", "").replace("-", "")
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError:
        raise SystemExit(f"错误：{name} 不是合法十六进制串：{text}")
    if len(raw) != expect_len:
        raise SystemExit(f"错误：{name} 需要 {expect_len} 字节，实际 {len(raw)} 字节")
    return raw


# ----------------------------- 构包 -----------------------------
def build_units(seq: int, chunk: bytes, cfg: dict) -> dict:
    """构造单包的各级别内容，返回 {"domain","pus","tfdz","tfdf","frame"}。"""
    n = cfg["data_len"]
    seq_fmt = ">H" if cfg["seq_endian"] == "big" else "<H"
    len_fmt = ">H" if cfg["len_endian"] == "big" else "<H"

    valid_len = len(chunk)
    data = chunk + bytes([cfg["pad"]]) * (n - valid_len)

    domain = struct.pack(seq_fmt, seq & 0xFFFF) + struct.pack(len_fmt, valid_len) + data   # N+4
    pus = cfg["pus_id"] + domain                                                            # N+6
    tfdz_body = cfg["tfdz_hdr"] + pus                                                       # N+17
    tfdf_body = cfg["tfdf_hdr"] + tfdz_body                                                 # N+20

    ecc = make_ecc(tfdf_body if cfg.get("ecc_scope", "tfdf") == "tfdf" else pus,
                   cfg["ecc"], cfg["len_endian"])                                           # 2B

    tfdz = tfdz_body + ecc                                                                  # N+19
    tfdf = tfdf_body + ecc                                                                  # N+22

    body = bytes([cfg["type_code"]]) + struct.pack(len_fmt, len(tfdf)) + tfdf
    checksum = sum(body) & 0xFF
    frame = SYNC + body + bytes([checksum])                                                 # N+28
    return {"domain": domain, "pus": pus, "tfdz": tfdz, "tfdf": tfdf, "frame": frame}


def build_frame(seq: int, chunk: bytes, cfg: dict) -> bytes:
    """构造单帧完整上注数据（N+28 字节）。"""
    return build_units(seq, chunk, cfg)["frame"]


def build_pus(seq: int, chunk: bytes, cfg: dict) -> bytes:
    """构造 PUS TC 消息包（5F01 + 序号 + 长度 + 数据，N+6 字节）。"""
    return build_units(seq, chunk, cfg)["pus"]


def generate(input_path: str, output_path: str, cfg: dict) -> dict:
    """将输入文件切分并封装为指定级别的包序列；level=all 时输出 5 个文件（文件名带包长）。"""
    level = cfg.get("level", "frame")
    n = cfg["data_len"]
    sz = sizes(n)

    file_size = os.path.getsize(input_path)
    last_valid = (file_size % n) or n
    seq = cfg["start_seq"]
    chunks = 0

    if level == "all":
        outs = {lv: level_filename(output_path, lv, n) for lv in ALL_LEVELS}
        files = {lv: open(p, "wb") for lv, p in outs.items()}
    else:
        outs = {level: output_path}
        files = {level: open(output_path, "wb")}
    out_files = outs

    try:
        with open(input_path, "rb") as fin:
            while True:
                chunk = fin.read(n)
                if not chunk:
                    break
                units = build_units(seq, chunk, cfg)
                for lv, fh in files.items():
                    fh.write(units[lv])
                chunks += 1
                seq = (seq + 1) & 0xFFFF
    finally:
        for fh in files.values():
            fh.close()

    unit = sz[level] if level != "all" else 0
    if level == "all":
        out_files = dict(outs)
        total = sum(os.path.getsize(p) for p in outs.values())
    else:
        out_files = outs
        total = os.path.getsize(output_path)
    return {
        "input": input_path,
        "output": output_path if level != "all" else str(outs),
        "output_files": out_files,
        "input_size": file_size,
        "frames": chunks,
        "unit_size": unit,
        "level": level,
        "data_len": n,
        "output_size": total,
        "last_valid": last_valid,
    }


# ----------------------------- 校验 -----------------------------
# 各级别包尾部不含数据域的字节数（frame=差错控制2+累加和1；tfdf/tfdz=差错控制2；pus/domain=0）
LEVEL_TRAILING = {"frame": 3, "tfdf": 2, "tfdz": 2, "pus": 0, "domain": 0}


def _dd_offset(level: str) -> int:
    """数据域（序号 2B）在各级别包内的起始偏移。"""
    if level == "frame":
        return DATA_DOMAIN_OFFSET                      # = 21（EB90+指令码+长度+TFDF导头+TFDZ导头+5F01）
    if level == "tfdf":
        return TFDF_HDR_LEN + TFDZ_HDR_LEN + 2         # = 16
    if level == "tfdz":
        return TFDZ_HDR_LEN + 2                        # = 13
    if level == "pus":
        return 2                                       # 5F01 之后
    return 0                                           # domain


def verify_pkg(package_path: str, level: str = "frame", data_len: int = PAYLOAD_SIZE,
               pus_id=b"\x5f\x01", type_code=None, endian: str = "big",
               ecc=None, ecc_scope: str = "tfdf") -> bool:
    """校验指定级别的包序列：序号连续性、长度字段、差错控制（可选）、末包 0x55 填充；
    完整帧额外检查同步头 / 指令码 / 长度字段 / 累加和。"""
    sz = sizes(data_len)
    unit = sz["frame" if level == "frame" else level]
    trailing = LEVEL_TRAILING[level]
    dd_ofs = _dd_offset(level)

    data = open(package_path, "rb").read()
    if len(data) % unit:
        print(f"[失败] 文件大小 {len(data)} 不是 {unit} 的整数倍")
        return False
    n = len(data) // unit
    if n == 0:
        print("[失败] 文件为空")
        return False

    seq_fmt = ">H" if endian == "big" else "<H"
    ok = True
    prev_seq = None
    for i in range(n):
        p = data[i * unit:(i + 1) * unit]
        if level == "pus":
            if p[:2] != pus_id:
                print(f"[失败] 第 {i+1} 包 PUS 标识异常: {p[:2].hex(' ')}")
                ok = False
        elif level == "frame":
            if p[:2] != SYNC:
                print(f"[失败] 第 {i+1} 帧同步头异常: {p[:2].hex(' ')}")
                ok = False
            if type_code is not None and p[2] != type_code:
                print(f"[失败] 第 {i+1} 帧指令码 {p[2]:#04x}，期望 {type_code:#04x}")
                ok = False
            tfdf_len = struct.unpack(">H", p[3:5])[0]
            if tfdf_len != sz["tfdf"]:
                print(f"[失败] 第 {i+1} 帧有效数据长度 {tfdf_len}，期望 {sz['tfdf']}")
                ok = False
            if (sum(p[2:unit - 1]) & 0xFF) != p[unit - 1]:
                print(f"[失败] 第 {i+1} 帧累加和错误")
                ok = False

        dd = p[dd_ofs:]
        seq = struct.unpack(seq_fmt, dd[0:2])[0]
        vlen = struct.unpack(">H", dd[2:4])[0]
        if prev_seq is not None and seq != ((prev_seq + 1) & 0xFFFF):
            print(f"[失败] 第 {i+1} 包序号 {seq} 不连续（上一包 {prev_seq}）")
            ok = False
        prev_seq = seq
        if not (1 <= vlen <= data_len):
            print(f"[失败] 第 {i+1} 包长度字段 {vlen} 越界")
            ok = False
        if i < n - 1 and vlen != data_len:
            print(f"[失败] 第 {i+1} 包（非末包）长度 {vlen} != {data_len}")
            ok = False

        # 包差错控制复算
        if ecc in ("crc16", "crc16-pus", "ccitt") and level in ("frame", "tfdf", "tfdz"):
            if level == "frame":
                body = p[5:unit - 3]                   # TFDF（含导头，不含ECC）
                ecc_ofs = unit - 3
                hdr_len = TFDF_HDR_LEN + TFDZ_HDR_LEN
            elif level == "tfdf":
                body = p[0:unit - 2]
                ecc_ofs = unit - 2
                hdr_len = TFDF_HDR_LEN + TFDZ_HDR_LEN
            else:                                      # tfdz
                body = p[0:unit - 2]
                ecc_ofs = unit - 2
                hdr_len = TFDZ_HDR_LEN
            scope_eff = "pus" if ecc_scope == "pus" else "tfdf"
            if scope_eff == "pus":
                covered = body[hdr_len:]               # 仅 PUS TC 消息
            elif level == "tfdz":
                covered = None                         # TFDF 导头不在 TFDZ 包内，无法复算
            else:
                covered = body                         # TFDF 整帧除 ECC 外
            if covered is not None:
                want = make_ecc(covered, ecc, endian)
                got = p[ecc_ofs:ecc_ofs + 2]
                if want != got:
                    print(f"[失败] 第 {i+1} 包差错控制 {got.hex(' ')} != 复算 {want.hex(' ')}")
                    ok = False

    last_vlen = struct.unpack(">H", data[(n - 1) * unit + dd_ofs + 2:
                                         (n - 1) * unit + dd_ofs + 4])[0]
    pad = data[(n - 1) * unit + dd_ofs + 4 + last_vlen: (n - 1) * unit + unit - trailing]
    if any(b != PAD_BYTE for b in pad):
        print("[失败] 末包填充字节不是 0x55")
        ok = False

    sofs = dd_ofs
    print("=" * 60)
    print(f"文件       : {package_path}")
    print(f"包类型     : {LEVEL_NAME.get(level, level)}（数据区 N={data_len} 字节，包长 {unit} 字节）")
    print(f"总包数     : {n}")
    print(f"首包序号   : {struct.unpack(seq_fmt, data[sofs:sofs + 2])[0]}")
    print(f"末包有效长 : {last_vlen} 字节（0x55 填充 {data_len - last_vlen} 字节）")
    print(f"校验结果   : {'通过' if ok else '失败'}")
    print("=" * 60)
    return ok


def detect_level(package_path: str, data_len: int = PAYLOAD_SIZE):
    """按文件大小猜测包级别，返回 level 名或 None。"""
    size = os.path.getsize(package_path)
    sz = sizes(data_len)
    for lv in ("frame", "tfdf", "tfdz", "pus", "domain"):
        if size and size % sz[lv] == 0:
            return lv
    return None


# 兼容旧接口
def verify(package_path: str, type_code=None, ecc=None, endian="big", data_len: int = PAYLOAD_SIZE) -> bool:
    return verify_pkg(package_path, "frame", data_len=data_len,
                      type_code=type_code, endian=endian)


def verify_pus(package_path: str, pus_id=b"\x5f\x01", endian: str = "big",
               data_len: int = PAYLOAD_SIZE) -> bool:
    return verify_pkg(package_path, "pus", data_len=data_len,
                      pus_id=pus_id, endian=endian)


def main():
    ap = argparse.ArgumentParser(description="最终上注数据生成程序（依据 8.5.2 表 8-6，支持 N 可变与四种输出级别）")
    ap.add_argument("input", nargs="?", help="输入二进制文件")
    ap.add_argument("-o", "--output", help="输出文件（默认 <输入名>_uplink<N+28>.bin；level=all 时作为文件名前缀）")
    ap.add_argument("--level", choices=LEVELS, default="frame",
                    help="输出级别：frame(完整帧)/tfdf/tfdz/pus/domain/all（默认 frame）")
    ap.add_argument("--data-len", type=lambda x: int(x, 0), default=PAYLOAD_SIZE,
                    help="数据区长度 N，默认 958（整帧 986 字节）")
    ap.add_argument("--type-code", type=lambda x: int(x, 0), default=0x0E,
                    help="指令码：0x0E 处理器上注（默认）/ 0x1E 高速Ku上注")
    ap.add_argument("--start-seq", type=lambda x: int(x, 0), default=1, help="数据域序号起始值（默认 1）")
    ap.add_argument("--seq-endian", choices=["big", "little"], default="big", help="序号字节序（默认 big）")
    ap.add_argument("--len-endian", choices=["big", "little"], default="big",
                    help="长度字段字节序，同时作用于配置与校验（默认 big）")
    ap.add_argument("--endian", choices=["big", "little"], help="同时设置序号与长度字节序")
    ap.add_argument("--tfdf-hdr", default="000000", help="TFDF 导头 3 字节，默认 000000")
    ap.add_argument("--tfdz-hdr", default="00" * TFDZ_HDR_LEN, help="TFDZ 导头 11 字节，默认全 00")
    ap.add_argument("--pus-id", default="5F01", help="PUS TC 消息标识，默认 5F01")
    ap.add_argument("--ecc", choices=ECC_MODES, default="crc16-pus",
                    help="包差错控制：crc16-pus(默认,仅覆盖PUS TC消息)/crc16(USLP规程,覆盖TFDF除ECC外)/zeros/sum16")
    ap.add_argument("--ecc-scope", choices=["tfdf", "pus"], default=None,
                    help="CRC 覆盖范围：pus(仅PUS TC消息)/tfdf(整帧除ECC)；不指定时 crc16-pus 默认 pus，其余默认 tfdf")
    ap.add_argument("--pad", type=lambda x: int(x, 0), default=PAD_BYTE, help="末帧填充字节，默认 0x55")
    ap.add_argument("--verify", metavar="FILE", help="仅校验已生成的包（自动识别级别）")
    args = ap.parse_args()

    ecc_scope = args.ecc_scope or ("pus" if args.ecc == "crc16-pus" else "tfdf")

    if args.verify:
        level = detect_level(args.verify, args.data_len)
        if level is None:
            print(f"[失败] 文件大小 {os.path.getsize(args.verify)} 与 N={args.data_len} 的各级别包长均不匹配")
            sys.exit(1)
        print(f"[自动识别] 包级别: {LEVEL_NAME.get(level, level)}")
        ok = verify_pkg(args.verify, level, data_len=args.data_len,
                        pus_id=parse_hex_bytes(args.pus_id, 2, "--pus-id"),
                        type_code=args.type_code & 0xFF, endian=args.seq_endian,
                        ecc=args.ecc, ecc_scope=ecc_scope)
        sys.exit(0 if ok else 1)

    if not args.input:
        ap.error("需要指定输入文件（或使用 --verify）")
    if not os.path.isfile(args.input):
        sys.exit(f"错误：输入文件不存在：{args.input}")

    seq_endian = args.endian or args.seq_endian
    len_endian = args.endian or args.len_endian

    cfg = {
        "type_code": args.type_code & 0xFF,
        "start_seq": args.start_seq,
        "seq_endian": seq_endian,
        "len_endian": len_endian,
        "tfdf_hdr": parse_hex_bytes(args.tfdf_hdr, TFDF_HDR_LEN, "--tfdf-hdr"),
        "tfdz_hdr": parse_hex_bytes(args.tfdz_hdr, TFDZ_HDR_LEN, "--tfdz-hdr"),
        "pus_id": parse_hex_bytes(args.pus_id, 2, "--pus-id"),
        "ecc": args.ecc,
        "ecc_scope": ecc_scope,
        "pad": args.pad & 0xFF,
        "data_len": args.data_len,
        "level": args.level,
    }

    sz = sizes(args.data_len)
    if args.level == "all":
        output = args.output or (os.path.splitext(args.input)[0] + "_packs.bin")
    else:
        output = args.output or level_filename(args.input, args.level, args.data_len)
    info = generate(args.input, output, cfg)

    print("=" * 60)
    print(f"最终上注数据生成完成（级别: {LEVEL_NAME[args.level]}）")
    print(f"  输入文件     : {info['input']} ({info['input_size']} 字节)")
    if args.level == "all":
        for lv, p in info["output_files"].items():
            print(f"  输出-{lv:<6}: {p} ({os.path.getsize(p)} 字节)")
    else:
        print(f"  输出文件     : {output} ({info['output_size']} 字节)")
    print(f"  总包数       : {info['frames']} 包 × {info['unit_size']} 字节")
    print(f"  末帧有效数据 : {info['last_valid']} 字节（不足 {args.data_len} 补 0x{cfg['pad']:02X}）")
    print(f"  数据区长度 N : {args.data_len}（数据域 {sz['domain']}B / PUS {sz['pus']}B / TFDZ {sz['tfdz']}B / TFDF {sz['tfdf']}B / 整帧 {sz['frame']}B）")
    print(f"  指令码       : 0x{cfg['type_code']:02X}")
    print(f"  起始序号     : {cfg['start_seq']}（{seq_endian} endian）")
    print(f"  包差错控制   : {cfg['ecc']}（覆盖: {'TFDF整帧除ECC' if ecc_scope == 'tfdf' else '仅PUS TC消息'}）")
    if args.level in ("frame", "tfdf", "tfdz", "all"):
        print(f"  导头         : TFDF={cfg['tfdf_hdr'].hex(' ')} / TFDZ={cfg['tfdz_hdr'].hex(' ')}")
    print("=" * 60)

    # 生成后立即自检
    if args.level == "all":
        for lv, p in info["output_files"].items():
            verify_pkg(p, lv, data_len=args.data_len, pus_id=cfg["pus_id"],
                       type_code=cfg["type_code"], endian=seq_endian)
    else:
        verify_pkg(output, args.level, data_len=args.data_len, pus_id=cfg["pus_id"],
                   type_code=cfg["type_code"], endian=seq_endian)


if __name__ == "__main__":
    main()
