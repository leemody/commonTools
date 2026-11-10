#!/usr/bin/env python3
"""将 DSL 旧 TC 帧转换为普通 USLP 遥控帧，仅依赖 Python 标准库。

运行：python rebuild_uslp_dsl_frame.py [../app]
路径相对于当前工作目录。每个应用生成 build/<app>.csv，源文件不改动。
CSV 的“遥控包数据域”列存放完整新 USLP 帧 HEX，每条一行，无 tcc/sleep。
rebuild_frame_file(path) 返回 list[str]，每项为完整新帧的空格分隔大写 HEX。

img.frame.dat：5F01 + 原包数据区（含 1C、业务校验及填充）。
img.offset.txt：保留原 5001 指令码及参数。
两类均移除旧 5B 帧头、6B 包头、2B 帧 CRC，重新计算包/帧 CRC。
"""

import argparse
import binascii
import csv
import os
from pathlib import Path


PID = 3
PCAT = 3
SCID = 0xFF01
SERVICE_TYPE = 2
SERVICE_SUBTYPE = 2


def crc16(data):
    """CRC-16/CCITT-FALSE: poly=1021, init=FFFF, xorout=0。"""
    return binascii.crc_hqx(data, 0xFFFF)


def append_crc(data):
    return data + crc16(data).to_bytes(2, "big")


def build_frame(command_code, parameters, vcf_count=0):
    """构造 VCID=5、MAP=0 的普通 USLP TC(2,2) 帧。"""
    app_data = command_code.to_bytes(2, "big") + parameters
    packet = append_crc(
        (0x1800 | (PID << 4) | PCAT).to_bytes(2, "big")
        + b"\xC0\x00"
        + (len(app_data) + 6).to_bytes(2, "big")
        + bytes((0x20, SERVICE_TYPE, SERVICE_SUBTYPE))
        + b"\x07\xF6"
        + app_data
    )
    frame_size = 43 + len(packet)
    if frame_size > 510:
        raise ValueError("新帧长 {} 字节，超过普通遥控帧上限 510".format(frame_size))
    word = (12 << 28) | (SCID << 12) | (1 << 11) | (5 << 5)
    return append_crc(
        word.to_bytes(4, "big")
        + (frame_size - 1).to_bytes(2, "big")
        + bytes((0x81, vcf_count & 0xFF))
        + b"\x5A" * 14
        + b"\xE0\xFF\xFF"
        + packet
        + b"\x5A" * 16
    )


def extract_business(frame):
    """校验本工具支持的旧帧布局，返回未经修改的包数据区。"""
    if len(frame) < 14:
        raise ValueError("旧帧长度不足")
    if frame[0] >> 6 != 0:
        raise ValueError("旧 TC 帧版本不是 0")
    if (int.from_bytes(frame[2:4], "big") & 0x3FF) + 1 != len(frame):
        raise ValueError("旧帧长度字段与实际长度不符")
    if crc16(frame[:-2]) != int.from_bytes(frame[-2:], "big"):
        raise ValueError("旧帧 CRC 校验失败")
    # 此 DSL 布局在 5B 帧头后直接放置空间包，没有额外段头。
    if frame[5:7] != b"\x10\x43":
        raise ValueError("不支持的旧空间包标识，预期 10 43")
    if int.from_bytes(frame[9:11], "big") + 7 != len(frame) - 7:
        raise ValueError("旧空间包长度字段与实际长度不符")
    return frame[11:-2]


def rebuild_frame_file(file_path):
    """读取 tcc 记录并返回新帧 HEX 列表；忽略 sleep、注释和空行。

    每个文件的 VCF 从 0 开始，按模 256 递增。缺失文件、坏帧会报错。
    """
    path = Path(file_path)
    if path.name.endswith(".img.frame.dat"):
        is_image = True
    elif path.name.endswith(".img.offset.txt"):
        is_image = False
    else:
        raise ValueError("不支持的文件名：{}".format(path))
    result = []
    # 仅解析 ASCII 指令；兼容注释使用 UTF-8、GBK 等编码的文件。
    for line_number, raw_line in enumerate(path.read_bytes().splitlines(), 1):
        parts = raw_line.strip().split(None, 1)
        if not parts or parts[0].lower() != b"tcc":
            continue
        try:
            if len(parts) != 2:
                raise ValueError("tcc 后没有数据")
            old = bytes.fromhex(parts[1].decode("ascii"))
            business = extract_business(old)
            if is_image:
                if not business.startswith(b"\x1C\xCC\x55"):
                    raise ValueError("镜像业务数据应以 1C CC 55 开头")
                command_code, parameters = 0x5F01, business
            else:
                if not business.startswith(b"\x50\x01"):
                    raise ValueError("offset 原指令码应为 5001")
                command_code, parameters = 0x5001, business[2:]
            frame = build_frame(command_code, parameters, len(result))
            result.append(" ".join("{:02X}".format(value) for value in frame))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("{}:{}: {}".format(path, line_number, exc)) from exc
    if not result:
        raise ValueError("{}: 未找到 tcc 指令".format(path))
    return result


def rebuild_apps(top_path="../app"):
    """遍历应用，合并镜像与 offset 指令并输出 UTF-8 BOM CSV。"""
    count = 0
    for app in sorted(os.listdir(top_path)):
        app_dir = os.path.join(top_path, app)
        if not os.path.isdir(app_dir) or app in ["build", "cmd"]:
            continue
        build_dir = os.path.join(app_dir, "build")
        ins_list1 = rebuild_frame_file(os.path.join(build_dir, app + ".img.frame.dat"))
        ins_list2 = rebuild_frame_file(os.path.join(build_dir, app + ".img.offset.txt"))
        output = os.path.join(build_dir, app + ".csv")
        with open(output, mode="w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["序号", "指令代号", "指令名称", "指令类型", "遥控帧"])
            idx = 1
            for kind, instructions in [("frame", ins_list1), ("offset", ins_list2)]:
                for number, instruction in enumerate(instructions, 1):
                    writer.writerow([
                        idx, "{}_{}_{}".format(app, kind, number),
                        "{}{}{}".format(app, "镜像上注" if kind == "frame" else "偏移设置", number),
                        "普通遥控", instruction,
                    ])
                    idx += 1
        count += 1
        print("{}: {} 条指令".format(output, idx - 1))
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("top_path", nargs="?", default="../app", help="应用根目录，默认 ../app")
    args = parser.parse_args()
    try:
        count = rebuild_apps(args.top_path)
    except (OSError, ValueError) as exc:
        parser.exit(1, "处理失败：{}\n".format(exc))
    print("完成，共处理 {} 个应用。".format(count))


if __name__ == "__main__":
    main()
