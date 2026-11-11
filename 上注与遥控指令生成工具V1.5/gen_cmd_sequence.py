# -*- coding: utf-8 -*-
"""按测试流程批量生成遥控指令清单。

用法：
    python gen_cmd_sequence.py [--out 输出目录]

输出：
    遥控指令清单_<日期>.txt   分组可读清单（参数 / 字节数 / HEX）
    遥控指令清单_<日期>.bin   全部指令帧按清单顺序拼接（可直接注入或脚本发送）

约定（依据《遥控包表模板-固存机械臂模块V4（公开）》）：
    帧 = EB 90 | 0F | n(2B) | 设备号 05 05 或 01 01 或 02 02 | 功能码(2B) | 参数 | 累加和
    n = 参数长度 + 4，整帧 n + 6 字节；累加和 = 从类型字 0x0F 起至末字节前求和取低 8 位。
    固存 APP 命令参数末尾固定字 AA AA；载荷类型为 24bit 位图，每 2bit 一类，b10=选通、b01=禁止。
    路由 FPGA 载荷选通参数为 16bit 位图，bit0~bit7 对应 8 路 VCID，1=接收、0=屏蔽。
"""
from __future__ import annotations

import os
import sys
import unicodedata
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import rcs_table as R  # noqa: E402

# --------------------------------------------------------------- 参数约定区
# 载荷类型：24bit 位图，每 2bit 一类，b10 表示选中该类
PAYLOADS = [
    ("光学相机数据", 0x000020),
    ("手眼相机图像", 0x000080),
    ("扩展监视相机数据", 0x000200),
    ("监视相机图像", 0x000800),
    ("高速KU上注数据", 0x002000),
    ("处理器上注数据", 0x008000),
    ("TOF B相机", 0x020000),
    ("TOF A相机", 0x080000),
    ("GNSS数据", 0x200000),
    ("全遥测数据", 0x800000),
]
PAYLOAD_NAME = {code: name for name, code in PAYLOADS}

MULTI_FILE = (0x008000, 0x002000)      # 这两个载荷按多文件编号，其余只操作 1 号文件
FILE_NOS = list(range(1, 102, 10))     # 1, 11, 21, …, 101
PLAYBACK_SN = 1                         # 回放相关流水号统一为 1
ONE_GB = 1024 ** 3                      # 1Gb = 0x40000000，7 字节存放

# 路由 FPGA 的 8 路 VCID（bit0~bit7）
VCIDS = [
    ("实时全遥测数据", 0),
    ("回放全遥测数据", 1),
    ("TOF A相机", 2),
    ("TOF B相机", 3),
    ("监视相机图像", 4),
    ("近程光学相机", 5),
    ("手眼相机图像", 6),
    ("GNSS", 7),
]

# 五个 APP 重构 Replace：序号 1/11/21/31/41 与 app 编号对应（行号为综合管理APP 表行号）
REFACTOR_APPS = [
    ("固存APP", 37, 1),
    ("监视相机APP", 38, 11),
    ("智能识别APP", 39, 21),
    ("机械臂控制APP", 40, 31),
    ("手眼相机APP", 41, 41),
]

# 同一 APP 有两种上注通道来源：KU 高速上注落在 upload1/，处理器上注落在 upload/
REFACTOR_CHANNELS = [
    ("KU", "高速KU上注", "/mnt/sda6/storage_ssd/upload1/upload1_{no:04d}.dat"),
    ("CPU", "处理器上注", "/mnt/sda6/storage_ssd/upload/upload_{no:04d}.dat"),
]

# 五个 APP 的 Replace 程序文件（与目录同名）
SHELL_TARGETS = [
    ("固存APP", "/opt/gc/gc_replace"),
    ("监视相机APP", "/opt/jsxj/jsxj_replace"),
    ("机械臂控制APP", "/opt/jxb/jxb_replace"),
    ("手眼相机APP", "/opt/syxj/syxj_replace"),
    ("智能识别APP", "/opt/znsb/znsb_replace"),
]
SHELL_DOWNLINK_ID = 0


# ------------------------------------------------------------------- 编码
def frame(payload: bytes) -> bytes:
    """EB 90 | 0F | n | payload | 累加和（累加和从类型字 0x0F 起算）。"""
    head = b"\xEB\x90\x0F" + len(payload).to_bytes(2, "big") + payload
    return head + bytes([sum(head[2:]) & 0xFF])


def fw(val: int, size: int) -> bytes:
    return int(val).to_bytes(size, "big", signed=False)


CAT, _REPORT = R.load_catalog()


def cmd(sheet: str, row: int) -> R.Cmd:
    for c in CAT:
        if c.sheet == sheet and c.row == row:
            return c
    raise KeyError(f"未找到指令 {sheet} 第 {row} 行")


def enc(sheet: str, row: int, **values) -> bytes:
    """按模板字段编码；字段名与表内一致。"""
    c = cmd(sheet, row)
    return R.assemble(c, values)


# ------------------------------------------------------------------- 清单
items = []          # (分组号, 分组标题, 指令名, 参数说明, 帧)


def add(group, gtitle, name, desc, data):
    items.append((group, gtitle, name, desc, data))


# 1 记录开始 / 记录停止
for label, row in (("记录开始", 11), ("记录停止", 12)):
    for pname, code in PAYLOADS:
        add(1, "记录开始 / 记录停止", f"固存APP {label}",
            f"载荷=0x{code:06X}（{pname}）", enc("固存APP", row, 载荷类型=code))

# 2 设置回放起点（各类载荷起点置 0）
for pname, code in PAYLOADS:
    add(2, "设置回放起点（起点=0）", "固存APP 设置回放起点",
        f"载荷=0x{code:06X}（{pname}） 流水号={PLAYBACK_SN} 起点=0",
        enc("固存APP", 5, 载荷类型=code, 流水号=PLAYBACK_SN, 回放起始点=0))

# 3 开始回放数据（单类载荷，流水号 1，数据量 0 = 全部）
for pname, code in PAYLOADS:
    add(3, "开始回放数据（数据量=0，回放全部）", "固存APP 开始回放数据",
        f"载荷=0x{code:06X}（{pname}） 流水号={PLAYBACK_SN} 数据量=0",
        enc("固存APP", 6, 载荷类型=code, 流水号=PLAYBACK_SN, 回放数据量=0))

# 4 选择回放（从 0 起回放 1Gb）
for pname, code in PAYLOADS:
    add(4, "选择回放（起点=0，长度=1Gb）", "固存APP 选择回放",
        f"载荷=0x{code:06X}（{pname}） 流水号={PLAYBACK_SN} 起点=0 数据量=0x{ONE_GB:X}(1Gb)",
        enc("固存APP", 7, 载荷类型=code, 流水号=PLAYBACK_SN,
            回放起始点=0, 回放数据量=ONE_GB))

# 5 终止回放
for pname, code in PAYLOADS:
    add(5, "终止回放", "固存APP 终止回放",
        f"载荷=0x{code:06X}（{pname}）", enc("固存APP", 8, 载荷类型=code))

# 6 删除载荷数据
for pname, code in PAYLOADS:
    nos = FILE_NOS if code in MULTI_FILE else [1]
    for no in nos:
        add(6, "删除载荷数据", "固存APP 删除载荷数据",
            f"载荷=0x{code:06X}（{pname}） 流水号(文件号)={no}",
            enc("固存APP", 10, 载荷类型=code, 流水号=no))

# 7 上注数据包写（仅 008000 / 002000，文件 1,11,…,101）
for pname, code in PAYLOADS:
    if code not in MULTI_FILE:
        continue
    for no in FILE_NOS:
        add(7, "上注数据包写", "固存APP 上注数据包写",
            f"载荷=0x{code:06X}（{pname}） 流水号(文件号)={no}",
            enc("固存APP", 13, 载荷类型=code, 流水号=no))

# 8 上注数据包写停
add(8, "上注数据包写停", "固存APP 上注数据包写停", "无参数", enc("固存APP", 14))

# 9 载荷数据选通（固存APP，24bit 位图）
for pname, code in PAYLOADS:
    add(9, "载荷数据选通（单独选通 / 单独禁止 / 全部）", "固存APP 载荷数据选通",
        f"选通 载荷=0x{code:06X}（{pname}）", enc("固存APP", 15, 载荷类型=code))
for pname, code in PAYLOADS:
    add(9, "载荷数据选通（单独选通 / 单独禁止 / 全部）", "固存APP 载荷数据选通",
        f"禁止 载荷=0x{code >> 1:06X}（{pname}）",
        enc("固存APP", 15, 载荷类型=code >> 1))
add(9, "载荷数据选通（单独选通 / 单独禁止 / 全部）", "固存APP 载荷数据选通",
    "所有载荷选通 载荷=0xAAAAAA", enc("固存APP", 15, 载荷类型=0xAAAAAA))
add(9, "载荷数据选通（单独选通 / 单独禁止 / 全部）", "固存APP 载荷数据选通",
    "所有载荷禁止 载荷=0x555555", enc("固存APP", 15, 载荷类型=0x555555))

# 10 路由 FPGA 复位 / 载荷选通 / 载荷屏蔽
ROUTE_SEL = 0x00FF
add(10, "路由FPGA 复位 / 载荷选通 / 载荷屏蔽", "路由 FPGA 复位", "无参数",
    frame(bytes.fromhex("0202A0B35A3C")))
for vname, bit in VCIDS:
    add(10, "路由FPGA 复位 / 载荷选通 / 载荷屏蔽", "路由 FPGA 载荷选通",
        f"仅选通 bit{bit}（{vname}） 位图=0x{1 << bit:04X}",
        frame(bytes.fromhex("0202A001") + fw(1 << bit, 2)))
for vname, bit in VCIDS:
    val = ROUTE_SEL & ~(1 << bit)
    add(10, "路由FPGA 复位 / 载荷选通 / 载荷屏蔽", "路由 FPGA 载荷选通",
        f"屏蔽 bit{bit}（{vname}） 位图=0x{val:04X}",
        frame(bytes.fromhex("0202A001") + fw(val, 2)))
add(10, "路由FPGA 复位 / 载荷选通 / 载荷屏蔽", "路由 FPGA 载荷选通",
    "所有载荷选通 位图=0x00FF", frame(bytes.fromhex("0202A001") + fw(0x00FF, 2)))
add(10, "路由FPGA 复位 / 载荷选通 / 载荷屏蔽", "路由 FPGA 载荷选通",
    "所有载荷屏蔽 位图=0x0000", frame(bytes.fromhex("0202A001") + fw(0x0000, 2)))

# 11 路由 FPGA PCIE / LVDS
add(11, "路由FPGA PCIE / LVDS", "路由 FPGA PCIE启动", "无参数",
    frame(bytes.fromhex("0202A004")))
add(11, "路由FPGA PCIE / LVDS", "路由 FPGA PCIE关闭", "无参数",
    frame(bytes.fromhex("0202A005")))
add(11, "路由FPGA PCIE / LVDS", "路由FPGA发送数传LVDS选择A", "无参数",
    frame(bytes.fromhex("0202A006")))
add(11, "路由FPGA PCIE / LVDS", "路由FPGA发送数传LVDS选择B", "无参数",
    frame(bytes.fromhex("0202A007")))

# 12 切换当前工作模式 1~9
for n in range(1, 10):
    add(12, "管理APP 切换当前工作模式", "管理APP-切换当前工作模式",
        f"模式序号={n} 确认={n}",
        enc("综合管理APP", 64, 启动模式序号=n, 启动模式序号确认B=n))

# 13 五个 APP 重构 Replace：每个 APP 两条（KU 通道 5 条 + 处理器通道 5 条）
for ch, chname, pattern in REFACTOR_CHANNELS:
    for app, row, no in REFACTOR_APPS:
        path = pattern.format(no=no)
        add(13, "APP 重构 Replace（KU 通道 5 条 + CPU 通道 5 条）",
            f"管理APP-{app}重构Replace-{ch}",
            f"通道={chname} 源文件={path}（{len(path)}B）",
            enc("综合管理APP", row, 源文件名=path))

# 14 Shell 删除 Replace 程序
for app, target in SHELL_TARGETS:
    text = f"rm -f {target}"
    add(14, "Shell 删除 APP 的 Replace 程序", f"管理APP-Shell 命令（{app}）",
        f"下传ID={SHELL_DOWNLINK_ID} 命令={text}（{len(text)}B）",
        enc("综合管理APP", 8, 下传ID=SHELL_DOWNLINK_ID, Shell命令字符串=text))


# ------------------------------------------------------------------- 输出
def dwidth(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, width: int) -> str:
    return s + " " * max(1, width - dwidth(s))


def verify(data: bytes) -> str:
    if data[:2] != b"\xEB\x90":
        return "帧头错误"
    if len(data) < 7:
        return "长度不足"
    n = int.from_bytes(data[3:5], "big")
    if n + 6 != len(data):
        return f"长度字不符({n}+6≠{len(data)})"
    if (sum(data[2:-1]) & 0xFF) != data[-1]:
        return "累加和错误"
    return ""


def main(argv):
    out_dir = HERE
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    stamp = datetime.now().strftime("%Y-%m-%d")
    txt_path = os.path.join(out_dir, f"遥控指令清单_{stamp}.txt")
    bin_path = os.path.join(out_dir, f"遥控指令清单_{stamp}.bin")

    groups, order = {}, []
    for g, gtitle, name, desc, data in items:
        if g not in groups:
            groups[g] = []
            order.append((g, gtitle))
        groups[g].append((name, desc, data))

    total = len(items)
    lines = []
    lines.append("=" * 118)
    lines.append("遥控指令清单（按测试流程分组）")
    lines.append(f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}    指令总数：{total} 条")
    lines.append("指令来源：《遥控包表模板-固存机械臂模块V4（公开）》 5 个工作表")
    lines.append("=" * 118)
    lines.append("")
    lines.append("帧结构：EB 90 | 0F | 有效数据长度 n(2B) | 设备号(2B) | 功能码(2B) | 参数 | 累加和(1B)")
    lines.append("        n = 参数长度 + 4，整帧 n + 6 字节；累加和 = 从类型字 0x0F 起求和取低 8 位；多字节字段大端")
    lines.append("载荷类型：24bit 位图，每 2bit 一类，b10=选通、b01=禁止、00=不关心")
    lines.append("          0x000020 光学 | 0x000080 手眼 | 0x000200 扩展监视 | 0x000800 监视 | 0x002000 高速KU")
    lines.append("          0x008000 处理器 | 0x020000 TOF B | 0x080000 TOF A | 0x200000 GNSS | 0x800000 全遥测")
    lines.append("路由 VCID：bit0 实时全遥测 | bit1 回放全遥测 | bit2 TOF A | bit3 TOF B | bit4 监视相机")
    lines.append("          bit5 近程光学 | bit6 手眼 | bit7 GNSS；位图 1=接收，0=屏蔽")
    lines.append("")

    bin_buf = bytearray()
    idx = 0
    bad = []
    for g, gtitle in order:
        rows = groups[g]
        lines.append("-" * 118)
        lines.append(f"【{g}】{gtitle}   （{len(rows)} 条）")
        lines.append("-" * 118)
        for name, desc, data in rows:
            idx += 1
            prefix = (f"{idx:03d}  " + pad(name, 30) + pad(desc, 60) + f"{len(data):>3}B  ")
            hexs = [f"{b:02X}" for b in data]
            chunks = [" ".join(hexs[i:i + 20]) for i in range(0, len(hexs), 20)]
            lines.append(prefix + chunks[0])
            for ch in chunks[1:]:
                lines.append(" " * dwidth(prefix) + ch)
            bin_buf += data
            err = verify(data)
            if err:
                bad.append((idx, name, err))
        lines.append("")

    lines.append("=" * 118)
    lines.append(f"合计 {idx} 条指令，共 {len(bin_buf)} 字节；同目录 .bin 为按此顺序拼接的指令流。")
    if bad:
        lines.append("以下指令自检未通过：")
        for it in bad:
            lines.append(f"  {it[0]:03d} {it[1]}  {it[2]}")
    else:
        lines.append("全部指令自检通过（帧头 / 长度字 / 累加和）。")
    lines.append("=" * 118)

    with open(txt_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\r\n".join(lines) + "\r\n")
    with open(bin_path, "wb") as f:
        f.write(bin_buf)

    print(f"清单：{txt_path}")
    print(f"指令流：{bin_path}")
    print(f"指令 {idx} 条，{len(bin_buf)} 字节，自检问题 {len(bad)} 条")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
