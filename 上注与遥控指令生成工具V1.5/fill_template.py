# -*- coding: utf-8 -*-
"""把 gen_cmd_sequence.py 生成的遥控指令，按《模板.xlsx》的列格式追加到表尾。

模板列（14 列）：
    1 发送方所属分系统   2 发送方设备名称   3 指令去向分系统   4 指令去向设备
    5 指令代号(ZBxxxx)   6 指令名称        7 类型(低速注数指令)   8 VCF计数
    9 遥控包序列标志     10 遥控包名称或序列计数   11 遥控包APID   12 指令码
    13 遥控包指令单元数据（= 设备号2B + 功能码2B + 参数，不含 EB90/类型字0F/长度字/累加和）
    14 综测预留

用法：
    python fill_template.py                 # 追加到 J:/812工作/模板.xlsx（先自动备份）
    python fill_template.py --rebuild-from ZB0144   # 先删掉上次追加段再重写（不重复追加）
    python fill_template.py --dry            # 只打印将要写入的行，不写文件
    python fill_template.py --target 其他.xlsx
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import openpyxl  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

import gen_cmd_sequence as G  # noqa: E402

DEFAULT_XLSX = r"J:/812工作/模板.xlsx"
SHEET = "固存机械臂"

# 模板固定列值（与表内已有行一致）
COL_SEND_SYS = "综电"
COL_SEND_DEV = "综合电子管理单元"
COL_RECV_SYS = "综电"
COL_RECV_DEV = "综合电子管理单元"
CMD_TYPE = "低速注数指令"
VCF = "0"
SEQ_FLAG = 11
PKG_NAME = "00000000000000"
APID = "00A3"
CMD_CODE = "5001"

PAYLOAD_SHORT = {
    0x000020: "光学相机",
    0x000080: "手眼相机",
    0x000200: "扩展监视",
    0x000800: "监视相机",
    0x002000: "高速KU",
    0x008000: "处理器",
    0x020000: "TOF B",
    0x080000: "TOF A",
    0x200000: "GNSS",
    0x800000: "全遥测",
}

RE_PAYLOAD = re.compile(r"载荷=0x([0-9A-F]{6})(?:（([^）]+)）)?")
RE_FILE = re.compile(r"流水号\(文件号\)=(\d+)")


def payload_of(frame: bytes) -> str:
    """EB 90 | 0F | n(2B) | payload | cs  ->  payload 的十六进制串（大写无空格）。"""
    return frame[5:-1].hex().upper()


def make_name(group: int, cname: str, desc: str) -> str:
    """按分组成员生成符合模板风格的业务名称。"""
    cname = cname.replace(" ", "")
    m = RE_PAYLOAD.search(desc)
    code = int(m.group(1), 16) if m else None
    if m and m.group(2):
        short = m.group(2)                    # 描述里已带中文载荷名时直接用
    else:
        short = PAYLOAD_SHORT.get(code, f"0x{code:06X}" if code is not None else "")

    if group == 1:                                  # 记录开始 / 记录停止
        return f"{cname}-{short}"
    if group == 2:
        return f"固存APP设置回放起点-{short}"
    if group == 3:
        return f"固存APP开始回放数据-{short}"
    if group == 4:
        return f"固存APP选择回放-{short}-1Gb"
    if group == 5:
        return f"固存APP终止回放-{short}"
    if group == 6:
        no = RE_FILE.search(desc).group(1)
        return f"固存APP删除载荷数据-{short}-{no}号文件"
    if group == 7:
        no = RE_FILE.search(desc).group(1)
        return f"固存APP上注数据包写-{short}-{no}号文件"
    if group == 8:
        return "固存APP上注数据包写停"
    if group == 9:
        if desc.startswith("所有载荷选通"):
            return "固存APP载荷数据选通-全部选通"
        if desc.startswith("所有载荷禁止"):
            return "固存APP载荷数据选通-全部禁止"
        if desc.startswith("禁止"):
            return f"固存APP载荷数据选通-禁止{short}"
        return f"固存APP载荷数据选通-选通{short}"
    if group == 10:
        if cname.endswith("复位"):
            return "路由FPGA复位"
        if cname.endswith("载荷选通"):
            if desc.startswith("所有载荷选通"):
                return "路由FPGA载荷选通-全部选通"
            if desc.startswith("所有载荷屏蔽"):
                return "路由FPGA载荷选通-全部屏蔽"
            mm = re.search(r"（(.+?)）", desc)
            vname = mm.group(1) if mm else ""
            bit = re.search(r"bit(\d)", desc).group(1)
            verb = "屏蔽" if desc.startswith("屏蔽") else "选通"
            return f"路由FPGA载荷{verb}-bit{bit}{vname}"
        return cname
    if group == 11:
        return {"路由 FPGA PCIE启动": "路由FPGA-PCIE启动",
                "路由 FPGA PCIE关闭": "路由FPGA-PCIE关闭",
                "路由FPGA发送数传LVDS选择A": "路由FPGA-数传LVDS选择A",
                "路由FPGA发送数传LVDS选择B": "路由FPGA-数传LVDS选择B"}.get(cname, cname)
    if group == 12:
        mode = re.search(r"模式序号=(\d)", desc).group(1)
        return f"管理APP切换当前工作模式-模式{mode}"
    if group == 13:
        return cname
    if group == 14:
        app = re.search(r"（(.+?)）", cname).group(1)
        return f"管理APP-Shell删除{app}的Replace程序"
    return cname


def build_rows(start_no: int):
    rows = []
    no = start_no
    for group, _gtitle, cname, desc, frame in G.items:
        rows.append({
            "code": f"ZB{no:04d}",
            "name": make_name(group, cname, desc),
            "data": payload_of(frame),
            "group": group,
            "desc": desc,
        })
        no += 1
    return rows


def copy_style(src, dst):
    """把已有行的单元格样式（字体/对齐/边框/填充/数字格式）复制到新行。"""
    if src.has_style:
        dst.font = src.font.copy()
        dst.alignment = src.alignment.copy()
        dst.border = src.border.copy()
        dst.fill = src.fill.copy()
        dst.number_format = src.number_format
        dst.protection = src.protection.copy()


def main(argv):
    target = DEFAULT_XLSX
    if "--target" in argv:
        target = argv[argv.index("--target") + 1]
    dry = "--dry" in argv
    # --rebuild-from ZB0144：先删掉上次追加的整段（编号 >= 该值），再重新追加
    rebuild_from = None
    if "--rebuild-from" in argv:
        rebuild_from = int(re.sub(r"\D", "", argv[argv.index("--rebuild-from") + 1]))

    wb = openpyxl.load_workbook(target)
    ws = wb[SHEET]

    # 找最后一条已有指令行（跳过表头两行）
    last = ws.max_row
    while last > 2 and all(ws.cell(row=last, column=c).value in (None, "")
                          for c in range(1, 14)):
        last -= 1

    if rebuild_from is not None:
        cut = None
        for rn in range(3, last + 1):
            v = str(ws.cell(row=rn, column=5).value or "").strip()
            m = re.fullmatch(r"ZB(\d+)", v)
            if m and int(m.group(1)) >= rebuild_from:
                cut = rn
                break
        if cut is None:
            print(f"未找到 ZB{rebuild_from:04d} 及之后的行，无需截断")
        else:
            n = last - cut + 1
            print(f"截断：删除第 {cut} ~ {last} 行（{n} 行，ZB 编号 >= {rebuild_from}）")
            if not dry:
                ws.delete_rows(cut, n)
            last = cut - 1

    last_no = 0
    for rn in range(3, last + 1):
        v = str(ws.cell(row=rn, column=5).value or "")
        m = re.fullmatch(r"ZB(\d+)", v.strip())
        if m:
            last_no = max(last_no, int(m.group(1)))

    rows = build_rows(last_no + 1)
    print(f"目标文件：{target}")
    print(f"已有指令末行：第 {last} 行，末编号 ZB{last_no:04d}")
    print(f"本次追加：{len(rows)} 条，编号 ZB{last_no + 1:04d} ~ ZB{last_no + len(rows):04d}")

    if dry:
        for r in rows:
            print(f"  {r['code']}  {r['name']:<34} {r['data']}")
        return 0

    # 备份原文件
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root, ext = os.path.splitext(target)
    backup = f"{root}_备份_{stamp}{ext}"
    shutil.copy2(target, backup)
    print(f"已备份原文件：{backup}")

    style_row = last
    height = ws.row_dimensions[style_row].height

    import math
    import unicodedata

    def dwidth(s):
        return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)

    rn = last + 1
    for r in rows:
        vals = [COL_SEND_SYS, COL_SEND_DEV, COL_RECV_SYS, COL_RECV_DEV,
                r["code"], r["name"], CMD_TYPE, VCF, SEQ_FLAG, PKG_NAME,
                APID, CMD_CODE, r["data"], None]
        for ci, v in enumerate(vals, start=1):
            c = ws.cell(row=rn, column=ci, value=v)
            copy_style(ws.cell(row=style_row, column=ci), c)
        # 名称超出 F 列宽(约37)时按行数加高，保证不截断
        lines = max(1, math.ceil(dwidth(r["name"]) / 37.0))
        ws.row_dimensions[rn].height = height * lines
        rn += 1

    wb.save(target)
    print(f"写入完成：第 {last + 1} ~ {rn - 1} 行，共 {len(rows)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
