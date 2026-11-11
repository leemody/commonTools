#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
遥控包表驱动编码模块
====================
读取《遥控包表模板-固存机械臂模块V3》工作簿，解析各工作表「遥控包数据」列的模板，
自动识别固定字节与 <字段> 占位符，按统一帧结构生成指令：

    EB 90 | 类型字 | 有效数据长度 n(2B) | 设备号(2B) | 功能码(2B) | 参数 | 累加和(1B)
    n = 参数长度 + 4，整帧 n + 6 字节，多字节字段一律大端
    累加和 = 类型字至参数末字节之和的低 8 位（可切换为含帧头）

模板语法（来自工作簿）：
    05 05 5A 5A 55 22 4A          —— 固定字节（末尾单字节若等于计算出的累加和，视为示例校验和，自动剔除）
    05 05 44 44 EE 71 <下传ID 1B> <长度 2B> <文件名> 累加和
    <源长度 2B> 与随后的 <源文件名> 自动联动：长度字段按文件名 ASCII 长度自动填写
    EB 90 0F <n> ...              —— 带帧头的模板（n 自动计算）

用法（命令行）：
    python rcs_table.py list [工作表]
    python rcs_table.py show <指令名关键字>
    python rcs_table.py selftest
    python rcs_table.py enc <指令名关键字> [--set 字段=值 ...]
"""

import os
import re
import struct
from dataclasses import dataclass, field as dc_field

DEFAULT_XLSX = r"I:\8004\working\5_XY\1_设计\6_遥控遥测\遥控包表模板-固存机械臂模块V4（公开）.xlsx"

HEADER = b"\xEB\x90"
DEFAULT_TYPE = 0x0F
HDR_SIZE = 6            # 帧头2 + 类型1 + 长度2 + 累加和1

TEXT_HINTS = ("名", "字符串", "命令", "路径", "值")
LENGTH_HINTS = ("长度", "字节数")


@dataclass
class Field:
    name: str
    size: int | None = None      # 固定字节数；None 表示随前一长度字段变化的字符串
    kind: str = "num"            # num / ascii / hexvar
    pair: int = -1               # 文本字段对应的长度字段索引
    default: int | None = None   # 从模板注释中提取的默认值（如 app序号 11）

    @property
    def is_length(self):
        return any(h in self.name for h in LENGTH_HINTS)

    @property
    def is_text(self):
        return self.kind != "num"


@dataclass
class Cmd:
    sheet: str
    row: int
    name: str
    desc: str
    type_code: int
    items: list                 # [('hex', bytes) | ('field', idx)]
    fields: list
    has_header: bool
    expected_cs: int = -1       # 模板末尾给出的示例累加和
    example: bytes = b""        # 「示例指令」列解析出的完整字节
    example_ok: bool = False
    defaults: dict = dc_field(default_factory=dict)

    @property
    def group(self):
        # 用功能码做分组：设备号后的 2 字节
        hexes = [b for k, b in self.items if k == "hex"]
        return self.sheet

    def fixed_prefix(self):
        out = bytearray()
        for kind, val in self.items:
            if kind == "hex":
                out += val
            else:
                break
        return bytes(out)


# ----------------------------------------------------------------- 模板解析
_ANNOT = re.compile(r"（[^）]*）|\([^)]*[\u4e00-\u9fff][^)]*\)")


def _make_field(spec: str) -> Field:
    s = spec.strip()
    m = re.search(r"(\d+)\s*B(?![0-9A-Za-z])", s)
    size = int(m.group(1)) if m else None
    name = s[:m.start()] if m else s
    name = re.split(r"[：:，,、（(]", name)[0].strip()
    name = re.sub(r"\d+\s*bit", "", name).strip()
    name = name.replace(" ", "") or s
    kind = "num"
    if size is None:
        if "值" in name:
            kind = "hexvar"
        elif any(h in name for h in TEXT_HINTS):
            kind = "ascii"
        else:
            size = 1          # 未标注长度的单字节字段（如表内 "确认B" 笔误）
    # 从注释中提取默认值，如 "<app序号1B：\n11，gc_golden;12, …>" → 0x11
    default = None
    m2 = re.search(r"[：:]\s*([0-9A-Fa-f]{1,4})(?![0-9A-Za-z])", s[m.end():] if m else s)
    if m2 and kind == "num" and (size or 1) <= 4:
        default = int(m2.group(1), 16)
    return Field(name=name, size=size, kind=kind, default=default)


SYMBOL_NAMES = {"M": "载荷类型", "K": "流水号", "S": "回放起始点", "V": "回放数据量"}


def parse_template(raw: str):
    """把「遥控包数据」文本解析为 (type_code, items, fields, has_header, expected_cs)。

    支持两种写法：
      A. <字段 2B> 占位符（综合管理APP / 固存APP 少数行）
      B. 符号式占位：MM MM MM（载荷类型 3B）、KK KK（流水号 2B）、
         SS×7（回放起点）、VV×7（回放数据量）、AA AA（结束标志字，字面量）、YY（累加和）
    """
    raw = str(raw)
    lines = raw.replace("\r", "").split("\n")
    keep = [lines[0]]
    # 首行存在未闭合的 "<...>" 字段注释时，跨行合并直到闭合（如 V4 表的 app序号）
    pending = lines[0].count("<") - lines[0].count(">")
    for ln in lines[1:]:
        if pending > 0:
            keep.append(ln)
            pending += ln.count("<") - ln.count(">")
            continue
        test = _ANNOT.sub(" ", ln).strip()
        if test and all(c in "0123456789abcdefABCDEF " for c in test):
            keep.append(ln)          # 跨行书写的长报文，续行只含十六进制
        else:
            break
    s = _ANNOT.sub(" ", " ".join(keep))
    i, n = 0, len(s)
    items, fields = [], []
    hexes = []
    has_cs_word = False
    n_placeholder = False
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if s.startswith("累加和", i):
            has_cs_word = True
            break
        if ch == "<":
            j = s.find(">", i)
            if j < 0:
                break
            f = _make_field(s[i + 1:j])
            i = j + 1
            if f.name.lower() == "n":
                n_placeholder = True
                continue
            fields.append(f)
            items.append(("field", len(fields) - 1))
            continue

        two = s[i:i + 2]
        # 符号式占位：MM / KK / SS / VV / YY
        if len(two) == 2 and two[0] == two[1] and two[0] in "MKVS":
            pairs = 0
            while s[i:i + 2] == two:
                pairs += 1
                i += 2
                while i < n and s[i] == " ":
                    i += 1
            f = Field(name=SYMBOL_NAMES[two[0]], size=pairs, kind="num")
            fields.append(f)
            items.append(("field", len(fields) - 1))
            continue
        if two == "YY":
            has_cs_word = True
            i += 2
            break
        if len(two) == 2 and all(c in "0123456789abcdefABCDEF" for c in two):
            hexes.append(int(two, 16))
            items.append(("hex", bytes([int(two, 16)])))
            i += 2
            continue
        break

    # 合并连续 hex 段
    merged = []
    for kind, val in items:
        if kind == "hex" and merged and merged[-1][0] == "hex":
            merged[-1] = ("hex", merged[-1][1] + val)
        else:
            merged.append((kind, val))
    items = merged

    # 帧头 / 类型字 / 字面长度字
    has_header = len(hexes) >= 2 and hexes[0] == 0xEB and hexes[1] == 0x90
    type_code = DEFAULT_TYPE
    if has_header:
        type_code = hexes[2] if len(hexes) > 2 else DEFAULT_TYPE
        items = _drop_prefix_bytes(items, 3)
        if not n_placeholder:
            items = _drop_literal_length(items, fields)

    # 末尾单字节：模板未写"累加和/YY"时视为示例校验和，剔除后由程序重算
    expected_cs = -1
    if not has_cs_word and items and items[-1][0] == "hex":
        tail = items[-1][1]
        if len(tail) >= 2 and len(default_hex(items)) >= 5:
            expected_cs = tail[-1]
            items = items[:-1] + [("hex", tail[:-1])]
        elif len(tail) == 1 and len(default_hex(items)) >= 5:
            expected_cs = tail[0]
            items = items[:-1]

    # 文本字段与长度字段配对
    for idx, f in enumerate(fields):
        if f.is_text:
            for j in range(idx - 1, -1, -1):
                if fields[j].is_length and fields[j].size:
                    f.pair = j
                    break
    return type_code, items, fields, has_header, expected_cs


def _drop_literal_length(items, fields=None):
    """带帧头的模板里若写了字面长度字（如 00 0B），按一致性判断后剔除。"""
    if not items or items[0][0] != "hex" or len(items[0][1]) < 3:
        return items
    head = items[0][1]
    n_val = (head[0] << 8) | head[1]
    total = sum(len(v) for k, v in items if k == "hex")
    if fields:
        total += sum((f.size or 0) for f in fields)
    # 模板可能含累加和字节（-3）也可能未写（-2）
    if n_val in (total - 2, total - 3):
        rest = head[2:]
        return ([("hex", rest)] if rest else []) + items[1:]
    return items


def default_hex(items):
    out = bytearray()
    for kind, val in items:
        if kind == "hex":
            out += val
    return bytes(out)


def _drop_prefix_bytes(items, count):
    out, dropped = [], 0
    for kind, val in items:
        if dropped < count and kind == "hex" and val:
            take = min(count - dropped, len(val))
            val = val[take:]
            dropped += take
            if not val:
                continue
        out.append((kind, val))
    return out


def _reindex(items, fields):
    """字段索引重排（fields 已过滤过 n 占位时使用）。"""
    mapping = {}
    new_fields = []
    for kind, val in items:
        if kind == "field":
            f = fields[val]
            if id(f) not in mapping:
                mapping[id(f)] = len(new_fields)
                new_fields.append(f)
    items = [("field", mapping[id(fields[val])]) if kind == "field" else (kind, val)
             for kind, val in items]
    return items


def _renumber(type_code, items, fields, has_header, expected_cs):
    mapping, new_fields = {}, []
    for kind, val in items:
        if kind == "field" and id(fields[val]) not in mapping:
            mapping[id(fields[val])] = len(new_fields)
            new_fields.append(fields[val])
    items = [("field", mapping[id(fields[val])]) if kind == "field" else (kind, val)
             for kind, val in items]
    for f in new_fields:
        if f.pair >= 0:
            f.pair = mapping.get(id(fields[f.pair]), -1)
    return items, new_fields


# ----------------------------------------------------------------- 编码 / 反解
def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def assemble(cmd: Cmd, values=None, cs_scope="body"):
    """按字段值组装整帧。values 可为 {字段名: 值}。"""
    vals = dict(cmd.defaults)
    if values:
        vals.update(values)

    blobs = {}
    for idx, f in enumerate(cmd.fields):
        raw = vals.get(f.name, 0 if f.kind == "num" else "")
        if f.kind == "ascii":
            b = raw.encode("ascii") if isinstance(raw, str) else bytes(raw)
            blobs[idx] = b
            if f.pair >= 0:
                vals[cmd.fields[f.pair].name] = len(b)
        elif f.kind == "hexvar":
            if isinstance(raw, str):
                b = bytes.fromhex(raw.replace(" ", "")) if raw.strip() else b""
            else:
                b = bytes(raw)
            blobs[idx] = b
            if f.pair >= 0:
                vals[cmd.fields[f.pair].name] = len(b)

    body = bytearray()
    for kind, val in cmd.items:
        if kind == "hex":
            body += val
            continue
        f = cmd.fields[val]
        if f.kind != "num":
            body += blobs.get(val, b"")
            continue
        num = int(vals.get(f.name, 0) or 0)
        body += int(num).to_bytes(f.size or 1, "big", signed=False)

    payload = bytes(body)
    n = len(payload)
    frame = HEADER + bytes([cmd.type_code]) + struct.pack(">H", n) + payload
    cs = checksum(frame if cs_scope == "frame" else frame[2:])
    return frame + bytes([cs])


def unassemble(cmd: Cmd, data: bytes):
    """把一段字节按模板拆回字段值（用于解析「示例指令」并以示例作为默认值）。"""
    body = data
    if body[:2] == HEADER:
        body = body[2:]
        if body:
            body = body[1:]              # 类型字
        if len(body) >= 2:
            body = body[2:]              # 有效数据长度
    body = body[:-1]                     # 去掉累加和
    vals, pos = {}, 0
    for kind, val in cmd.items:
        if kind == "hex":
            seg = body[pos:pos + len(val)]
            if seg != val:
                return None
            pos += len(val)
            continue
        f = cmd.fields[val]
        if f.kind in ("ascii", "hexvar"):
            if f.pair < 0:
                return None
            ln = int(vals.get(cmd.fields[f.pair].name, 0))
            seg = body[pos:pos + ln]
            pos += ln
            vals[f.name] = seg.decode("ascii", "replace") if f.kind == "ascii" else seg.hex().upper()
        else:
            size = f.size or 1
            seg = body[pos:pos + size]
            if len(seg) != size:
                return None
            pos += size
            vals[f.name] = int.from_bytes(seg, "big")
    if pos != len(body):
        return None
    return vals


# ----------------------------------------------------------------- 工作簿加载
def _cell_text(ws, row, col):
    v = ws.cell(row=row, column=col).value
    return "" if v is None else str(v)


def load_catalog(path=DEFAULT_XLSX, verbose=False):
    """读取工作簿，返回 (catalog, report)。report 记录解析与回验结果。"""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    catalog, report = [], []
    for ws in wb.worksheets:
        # 表头行：第一行；数据从第 3 行开始（第 2 行为填写说明）
        for rn in range(3, ws.max_row + 1):
            name = _cell_text(ws, rn, 6).strip()
            tpl = _cell_text(ws, rn, 9).strip()
            ex = _cell_text(ws, rn, 11).strip()
            if not name or not tpl:
                continue
            try:
                type_code, items, fields, has_header, exp_cs = parse_template(tpl)
                items, fields = _renumber(type_code, items, fields, has_header, exp_cs)
            except Exception as e:                       # noqa: BLE001
                report.append((ws.title, rn, name, "模板解析失败", str(e)))
                continue
            cmd = Cmd(sheet=ws.title, row=rn, name=name, desc=ex,
                      type_code=type_code, items=items, fields=fields,
                      has_header=has_header, expected_cs=exp_cs)
            # 模板注释里给出的默认值（如 app序号 0x11）
            for f in fields:
                if f.default is not None:
                    cmd.defaults.setdefault(f.name, f.default)
            # 用示例指令回验并取默认值
            ex_bytes = _example_bytes(ex)
            if ex_bytes:
                cmd.example = ex_bytes
                vals = unassemble(cmd, ex_bytes)
                if vals is not None:
                    cmd.defaults = vals
                    try:
                        again = assemble(cmd, vals)
                    except Exception:                     # noqa: BLE001
                        again = b""
                    # 示例可能带帧头，也可能只写"设备号起"的载荷
                    cmd.example_ok = (again == ex_bytes
                                      or again[5:] == ex_bytes
                                      or again[2:] == ex_bytes)
                if not cmd.example_ok:
                    report.append((ws.title, rn, name, "示例回验不一致",
                                   ex_bytes.hex(" ").upper()))
            else:
                # 无单独示例：模板本身即实码，用默认值重建并与模板给出的校验和比对
                try:
                    frame = assemble(cmd, {})
                except Exception:                         # noqa: BLE001
                    frame = b""
                if cmd.expected_cs < 0:
                    report.append((ws.title, rn, name, "无示例指令", ""))
                elif frame and frame[-1] == cmd.expected_cs:
                    cmd.example_ok = True
                else:
                    calc = frame[-1] if frame else 0
                    report.append((ws.title, rn, name, "校验和与模板不符",
                                   f"模板={cmd.expected_cs:02X} 计算={calc:02X}"))
            catalog.append(cmd)
    if verbose:
        print(f"共解析 {len(catalog)} 条指令，回验问题 {len(report)} 条")
        for item in report:
            print("  ", item)
    return catalog, report


def _example_bytes(text: str):
    s = str(text or "").replace("\n", " ").replace("\r", " ")
    s = _ANNOT.sub(" ", s)
    s = re.sub(r"[（(][^）)]*[)）]", " ", s)
    out = bytearray()
    for token in s.split():
        t = token.strip().rstrip("，。；;,.")
        if len(t) % 2 == 0 and t and all(c in "0123456789abcdefABCDEF" for c in t):
            out += bytes.fromhex(t)
    return bytes(out) if out else b""


# ----------------------------------------------------------------- 命令行
def _main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    op = argv[0]
    xlsx = os.environ.get("RCS_XLSX", DEFAULT_XLSX)
    if op == "list":
        cat, _ = load_catalog(xlsx)
        want = argv[1] if len(argv) > 1 else None
        cur = None
        for c in cat:
            if want and want not in c.sheet:
                continue
            if c.sheet != cur:
                cur = c.sheet
                print(f"\n===== {cur} =====")
            print(f"  [{c.row:>3}] {c.name:<44} 类型={c.type_code:02X} "
                  f"{'示例OK' if c.example_ok else ('无示例' if not c.example else '回验失败')}")
        return 0
    if op == "selftest":
        cat, rep = load_catalog(xlsx)
        ok = sum(1 for c in cat if c.example_ok)
        noex = sum(1 for c in cat if not c.example)
        print(f"指令总数 {len(cat)}，示例回验通过 {ok}，无示例 {noex}，问题 {len(rep)}")
        for item in rep:
            print("   ", item)
        return 0 if not rep else 1
    if op == "enc":
        cat, _ = load_catalog(xlsx)
        kw = argv[1]
        cands = [c for c in cat if kw in c.name]
        if not cands:
            print("未找到匹配指令")
            return 2
        cmd = cands[0]
        values = {}
        for kv in argv[2:]:
            if kv.startswith("--set"):
                continue
            if "=" in kv:
                k, v = kv.split("=", 1)
                values[k] = v
        data = assemble(cmd, values)
        print(f"{cmd.sheet} / {cmd.name}  {len(data)} 字节")
        print(" ".join(f"{b:02X}" for b in data))
        return 0
    print(f"未知子命令：{op}")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
