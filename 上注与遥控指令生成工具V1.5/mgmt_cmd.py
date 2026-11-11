#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理APP 遥控指令编码模块（设备号 0x0505 综合管理APP）
=====================================================
帧结构（多字节字段一律大端，总长 = n + 6）：
    1~2   帧头            EB 90
    3     遥控指令/注数   0F
    4~5   有效数据长度 n   n = 设备号(2) + 功能码(2) + 功能参数 P = P + 4
    6~7   设备号          05 05（综合管理APP）
    8~9   功能码          2B，见下表
    10..n+5 功能参数 P
    n+6   累加和          从类型字 0x0F 起（含长度字）累加到参数末字节，取低 8 位

    累加和默认不含帧头（从 0x0F 起算）；如需含帧头（从 0xEB 起），
    传 include_header=True 或在界面切换。

功能参数 P 的构成：
    固定指令          ：APP 标识等固定字节
    重构 Replace      ：APP 标识 + 源长度(2B 大端) + 源文件名(ASCII)
    发送 FPGA-GOLDEN  ：副本号(1B) + 起始帧号(2B) + 结束帧号(2B) + 帧间隔(2B)
    发送 FPGA-Normal/Replace ：起始帧号(2B) + 结束帧号(2B) + 帧间隔(2B)

可选附加字（trailing）：部分固存指令参数末尾固定 0xAAAA，路由 FPGA 部分含 0x5A3C，
由使用者按具体指令决定是否追加，工具默认不追加。

命令行用法：
    python mgmt_cmd.py list
    python mgmt_cmd.py enc app1_kill
    python mgmt_cmd.py enc app2_refactor_replace --path /mnt/sda6/storage_ssd/upload1/upload1_0002.dat
    python mgmt_cmd.py enc fpga_send_golden --copy-no 1 --start 1 --end 4892 --interval 2
    python mgmt_cmd.py enc app1_kill --trailing AAAA --cs-scope frame
    python mgmt_cmd.py selftest
"""

import struct
from dataclasses import dataclass, field

HEADER = b"\xEB\x90"     # 帧头
TYPE_CODE = 0x0F         # 遥控指令/注数
DEVICE_ID = b"\x05\x05"  # 设备号：综合管理APP
MIN_LEN = 4              # n 最小 = 设备号 2 + 功能码 2

# 应用编号 / 名称 / 强制退出参数前字节 / 强制退出参数后字节
APPS = [
    (1, "固存APP",       0x55, 0x22),
    (2, "监视相机APP",   0xAA, 0x32),
    (3, "智能识别APP",   0x55, 0x23),
    (4, "机械臂控制APP", 0xAA, 0x33),
    (5, "手眼相机APP",   0x55, 0x24),
]


@dataclass
class Cmd:
    cid: str                     # 内部标识
    group: str                   # 分组（界面左侧树节点）
    name: str                    # 指令名
    desc: str                    # 功能说明
    code: bytes                  # 设备号(2B) + 功能码(2B)
    params: bytes = b""          # 固定功能参数
    kind: str = "fixed"          # fixed / path / fpga / fpga_copy
    doc_cs: int = -1             # 文档表中给出的累加和（-1 表示表内未给出）
    extra: dict = field(default_factory=dict)

    @property
    def device(self):
        return self.code[:2]

    @property
    def func(self):
        return self.code[2:]


def _build_table():
    cmds = []
    dev = DEVICE_ID

    # ---------- 1. 应用强制退出（功能码 5A5A）----------
    kill_cs = {1: 0x4A, 2: 0xAF, 3: 0x4B, 4: 0xB0, 5: 0x4C}
    for idx, app, p0, p1 in APPS:
        cmds.append(Cmd(
            cid=f"app{idx}_kill",
            group="应用强制退出",
            name=f"管理APP-{app}强制退出",
            desc=f"APP{idx} 软件强制退出(kill)",
            code=dev + b"\x5A\x5A",
            params=bytes([p0, p1]),
            doc_cs=kill_cs[idx],
        ))

    # ---------- 2~4. 从各分区加载（功能码 1111）----------
    zones = [
        ("Golden", 0x33, "golden", "从 Golden 区加载",
         {1: 0x75, 2: 0x76, 3: 0x77, 4: 0x78, 5: 0x79}),
        ("Normal", 0x11, "normal", "从 Normal 区加载",
         {1: 0x53, 2: 0x54, 3: 0x55, 4: 0x56, 5: 0x57}),
        ("Replace", 0x22, "replace", "从 Replace 区加载",
         {1: 0x64, 2: 0x65, 3: 0x66, 4: 0x67, 5: 0x68}),
    ]
    for zone_name, zone_param, zone_key, verb, cs_map in zones:
        for idx, app, _p0, _p1 in APPS:
            cmds.append(Cmd(
                cid=f"app{idx}_load_{zone_key}",
                group=f"加载 {zone_name} 区",
                name=f"管理APP-{app}加载{zone_name}",
                desc=f"{verb}{app}",
                code=dev + b"\x11\x11",
                params=bytes([zone_param, idx]),
                doc_cs=cs_map[idx],
            ))

    # ---------- 5. 重构到 Normal（功能码 5555，参数 11 0X）----------
    ref_normal_cs = {1: 0xDB, 2: 0xDC, 3: 0xDD, 4: 0xDE, 5: 0xDF}
    for idx, app, _p0, _p1 in APPS:
        cmds.append(Cmd(
            cid=f"app{idx}_refactor_normal",
            group="重构到 Normal 区",
            name=f"管理APP-{app}重构Normal",
            desc=f"将{app}重构到 Normal 区",
            code=dev + b"\x55\x55",
            params=bytes([0x11, idx]),
            doc_cs=ref_normal_cs[idx],
        ))

    # ---------- 6. 重构到 Replace（功能码 5555，参数 22 0X + 源长度 + 源文件名）----------
    for idx, app, _p0, _p1 in APPS:
        cmds.append(Cmd(
            cid=f"app{idx}_refactor_replace",
            group="重构到 Replace 区",
            name=f"管理APP-{app}重构Replace",
            desc=f"将{app}重构到 Replace 区（源长度 2B + 源文件名 ASCII）",
            code=dev + b"\x55\x55",
            params=bytes([0x22, idx]),
            kind="path",
        ))

    # ---------- 7~8. 校验文件版本（功能码 4444）----------
    for zone_name, zone_param, zone_key in [("Normal", 0x11, "normal"),
                                            ("Replace", 0x22, "replace")]:
        table_cs = ({1: 0xB9, 2: 0xBA, 3: 0xBB, 4: 0xBC, 5: 0xBD} if zone_key == "normal"
                    else {1: 0xCA, 2: 0xCB, 3: 0xCC, 4: 0xCD, 5: 0xCD})
        for idx, app, _p0, _p1 in APPS:
            cmds.append(Cmd(
                cid=f"app{idx}_verify_{zone_key}",
                group=f"校验 {zone_name} 区版本",
                name=f"管理APP-{app}校验{zone_name}",
                desc=f"校验 {zone_name} 区{app}文件版本(MD5)",
                code=dev + b"\x44\x44",
                params=bytes([zone_param, idx]),
                doc_cs=table_cs[idx],
            ))

    # ---------- 9~12. 发送 FPGA 文件（功能码 6666）----------
    cmds.append(Cmd(
        cid="fpga_send_golden",
        group="FPGA 文件操作",
        name="管理APP-发送FPGA-GOLDEN文件",
        desc="发送 FPGA GOLDEN 文件（副本号 1B + 起始/结束帧号 2B + 帧间隔 2B）",
        code=dev + b"\x66\x66",
        params=b"\x11\x01",
        kind="fpga_copy",
    ))
    cmds.append(Cmd(
        cid="fpga_send_normal",
        group="FPGA 文件操作",
        name="管理APP-发送FPGA-Normal文件",
        desc="发送 FPGA Normal 文件（起始/结束帧号 2B + 帧间隔 2B）",
        code=dev + b"\x66\x66",
        params=b"\x11\x02",
        kind="fpga",
    ))
    cmds.append(Cmd(
        cid="fpga_send_replace",
        group="FPGA 文件操作",
        name="管理APP-发送FPGA-Replace文件",
        desc="发送 FPGA Replace 文件（起始/结束帧号 2B + 帧间隔 2B）",
        code=dev + b"\x66\x66",
        params=b"\x11\x03",
        kind="fpga",
    ))
    cmds.append(Cmd(
        cid="fpga_send_stop",
        group="FPGA 文件操作",
        name="管理APP-停止发送FPGA文件",
        desc="停止发送 FPGA 文件（无功能参数）",
        code=dev + b"\x66\x66",
        params=b"\x11\x04",
    ))

    # ---------- 13~15. 校验 FPGA 版本（功能码 6666）----------
    cmds.append(Cmd(
        cid="fpga_verify_golden",
        group="FPGA 文件操作",
        name="管理APP-校验FPGA-GOLDEN版",
        desc="校验 FPGA GOLDEN 区文件版本(MD5)",
        code=dev + b"\x66\x66",
        params=b"\x22\x01",
    ))
    cmds.append(Cmd(
        cid="fpga_verify_normal",
        group="FPGA 文件操作",
        name="管理APP-校验FPGA-Normal版",
        desc="校验 FPGA Normal 区文件版本(MD5)",
        code=dev + b"\x66\x66",
        params=b"\x22\x02",
    ))
    cmds.append(Cmd(
        cid="fpga_verify_replace",
        group="FPGA 文件操作",
        name="管理APP-校验FPGA-Replace版",
        desc="校验 FPGA Replace 区文件版本(MD5)",
        code=dev + b"\x66\x66",
        params=b"\x22\x03",
    ))

    # ---------- 16. Replace 转 Normal（功能码 6666）----------
    cmds.append(Cmd(
        cid="fpga_replace_to_normal",
        group="FPGA 文件操作",
        name="管理APP-FPGA-Replace转为Normal版",
        desc="FPGA Replace 区转为 Normal 版",
        code=dev + b"\x66\x66",
        params=b"\x33\x01",
    ))

    return cmds


COMMANDS = _build_table()
BY_ID = {c.cid: c for c in COMMANDS}


def checksum(body: bytes) -> int:
    """累加和：给定区段字节和的低 8 位。"""
    return sum(body) & 0xFF


def build_frame(cmd: Cmd, params: bytes, include_header=False, trailing=b"") -> bytes:
    """按帧结构组装完整报文：EB90 | 0F | n | 设备号 | 功能码 | 参数 | 累加和。"""
    params = bytes(params) + bytes(trailing)
    n = MIN_LEN + len(params)
    if n > 0xFFFF:
        raise ValueError("有效数据长度超限")
    body = bytes([TYPE_CODE]) + struct.pack(">H", n) + cmd.device + cmd.func + params
    frame = HEADER + body
    cs = checksum(frame if include_header else body)
    return frame + bytes([cs])


def encode(cid, path=None, copy_no=None, start_frame=None, end_frame=None,
           interval=None, endian="big", include_header=False, trailing=b"",
           with_checksum=True):
    """构造一条指令帧，返回完整字节（含帧头与累加和）。"""
    cmd = BY_ID.get(cid)
    if cmd is None:
        raise ValueError(f"未知指令标识：{cid}")

    params = bytearray(cmd.params)
    fmt = ">H" if endian.lower().startswith("b") else "<H"

    if cmd.kind == "path":
        if not path:
            raise ValueError("该指令需要源文件名（--path）")
        raw = path.encode("ascii") if isinstance(path, str) else bytes(path)
        if len(raw) > 0xFFFF:
            raise ValueError("源文件名过长")
        params += struct.pack(fmt, len(raw))
        params += raw
    elif cmd.kind in ("fpga", "fpga_copy"):
        if cmd.kind == "fpga_copy":
            if copy_no is None:
                raise ValueError("该指令需要副本号（--copy-no）")
            if not 0 <= int(copy_no) <= 0xFF:
                raise ValueError("副本号应为 0~255")
            params.append(int(copy_no) & 0xFF)
        for label, flag, val in (("起始帧号", "--start", start_frame),
                                 ("结束帧号", "--end", end_frame),
                                 ("帧间隔", "--interval", interval)):
            if val is None:
                raise ValueError(f"该指令需要{label}（{flag}）")
            if not 0 <= int(val) <= 0xFFFF:
                raise ValueError(f"{label}应为 0~65535")
            params += struct.pack(fmt, int(val))

    frame = build_frame(cmd, params, include_header=include_header, trailing=trailing)
    if not with_checksum:
        frame = frame[:-1] + b"\x00"
    return frame


def split_fields(data: bytes, cmd: Cmd):
    """把报文拆分字段，返回 [(字段名, 字节, 说明文字|None)]。"""
    out = []
    if len(data) < 10:
        return [("原始数据", data, None)]
    n = struct.unpack(">H", data[3:5])[0]
    out.append(("帧头", data[0:2], ""))
    out.append(("类型字", data[2:3], "遥控指令/注数 0x0F"))
    out.append(("有效数据长度 n", data[3:5], str(n)))
    out.append(("设备号", data[5:7], "综合管理APP"))
    out.append(("功能码", data[7:9], ""))
    param = data[9:9 + (n - MIN_LEN)]
    if param:
        out.append(("功能参数", param, f"{len(param)} 字节"))
    out.append(("累加和", data[-1:], ""))
    return out


def selftest(verbose=True):
    """用文档表内给出的实码校验帧结构与累加和。返回 (通过数, 总数, 差异列表)。"""
    ok = bad = 0
    diffs = []
    for c in COMMANDS:
        if c.doc_cs < 0:
            continue
        frame = build_frame(c, c.params)
        cal = frame[-1]
        if cal == c.doc_cs:
            ok += 1
        else:
            bad += 1
            diffs.append((c.name, c.doc_cs, cal,
                          " ".join(f"{b:02X}" for b in frame)))
        if verbose:
            flag = "OK " if cal == c.doc_cs else "差异"
            print(f"[{flag}] {c.name:<34} {' '.join(f'{b:02X}' for b in frame)}  "
                  f"表内={c.doc_cs:02X} 计算={cal:02X}")
    if verbose:
        print(f"\n合计：一致 {ok} 条，差异 {bad} 条")
        for name, doc, cal, fr in diffs:
            print(f"  差异 -> {name}  表内 {doc:02X} / 计算 {cal:02X}   ({fr})")
    return ok, ok + bad, diffs


def _main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    op = argv[0]
    if op == "list":
        groups = {}
        for c in COMMANDS:
            groups.setdefault(c.group, []).append(c)
        for g, items in groups.items():
            print(f"\n== {g} ==")
            for c in items:
                cs = f"{c.doc_cs:02X}" if c.doc_cs >= 0 else "--"
                kind = {"fixed": "", "path": " +源长度+源文件名", "fpga": " +帧号/间隔",
                        "fpga_copy": " +副本号+帧号/间隔"}[c.kind]
                print(f"  {c.cid:<26} {c.name:<30} "
                      f"设备号/功能码={' '.join(f'{b:02X}' for b in c.code)} cs={cs}  "
                      f"{c.desc}{kind}")
        return 0
    if op == "selftest":
        ok, total, diffs = selftest()
        return 0 if ok == total else 1
    if op in ("enc", "encode"):
        import argparse
        ap = argparse.ArgumentParser(prog="mgmt_cmd.py enc")
        ap.add_argument("cid")
        ap.add_argument("--path", help="源文件名，如 /mnt/sda6/storage_ssd/upload1/upload1_0002.dat")
        ap.add_argument("--copy-no", type=int, help="副本号 0~255（GOLDEN 发送用）")
        ap.add_argument("--start", type=int, help="起始帧号")
        ap.add_argument("--end", type=int, help="结束帧号")
        ap.add_argument("--interval", type=int, help="帧间隔")
        ap.add_argument("--endian", default="big", choices=["big", "little"],
                        help="源长度/帧号字节序，默认 big")
        ap.add_argument("--trailing", default="", help="参数末尾附加字（HEX），如 AAAA 或 5A3C")
        ap.add_argument("--cs-scope", default="body", choices=["body", "frame"],
                        help="累加和范围：body=不含帧头(默认) / frame=含帧头")
        ap.add_argument("-o", "--output", help="可选：把生成报文写入该文件")
        a = ap.parse_args(argv[1:])
        trailing = bytes.fromhex(a.trailing.replace(" ", "")) if a.trailing else b""
        data = encode(a.cid, path=a.path, copy_no=a.copy_no,
                      start_frame=a.start, end_frame=a.end, interval=a.interval,
                      endian=a.endian, include_header=(a.cs_scope == "frame"),
                      trailing=trailing)
        n = struct.unpack(">H", data[3:5])[0]
        print(f"{BY_ID[a.cid].name}  共 {len(data)} 字节（n={n}，总长=n+6）")
        print(" ".join(f"{b:02X}" for b in data))
        if a.output:
            with open(a.output, "wb") as f:
                f.write(data)
            print(f"已写入 {a.output}")
        return 0
    print(f"未知子命令：{op}（可用：list / enc / selftest）")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
