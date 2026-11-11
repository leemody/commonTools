#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终上注数据生成工具 —— 图形界面
================================
调用 make_final_uplink.py 的帧构造逻辑，为二进制文件生成两种输出：
  1) 完整 986 字节/帧上注数据（EB90 + 指令码 + 长度 + TFDF/TFDZ 导头 + 5F01 + 数据域 + 差错控制 + 累加和）
  2) 仅数据域包 964 字节/包（5F 01 + 序号 2B + 长度 2B + 数据 958B，对应表 8-6 第 20~983 字节）
依赖：Python 3.8+ 自带 tkinter，无需安装第三方库。
运行：双击本文件，或 python uplink_gui.py
"""

import contextlib
import io
import os
import queue
import sys
import threading
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from make_final_uplink import (  # noqa: E402
    FRAME_SIZE, PUS_SIZE, PAYLOAD_SIZE, DATA_DOMAIN_OFFSET, PAD_BYTE,
    build_units, verify_pkg, sizes, ALL_LEVELS, level_filename, LEVEL_NAME, detect_level,
    parse_hex_bytes, TFDZ_HDR_LEN,
)
from mgmt_cmd import (  # noqa: E402
    COMMANDS, BY_ID, encode as cmd_encode,
    split_fields as cmd_split, HEADER, TYPE_CODE, MIN_LEN,
)
import rcs_table  # noqa: E402

RCS_XLSX_DEFAULT = rcs_table.DEFAULT_XLSX

APP_TITLE = "上注与遥控指令生成工具  V1.5  (帧/TFDF/TFDZ/PUS/数据域五级输出 · CRC-16 · 管理APP指令 · 全部遥控指令)"
PROGRESS_CHUNK = 958 * 200          # 每读取多少字节刷新一次进度
SAMPLE_PATH = "/mnt/sda6/storage_ssd/upload1/upload1_0002.dat"

KIND_LABEL = {
    "fixed": "固定指令（无参数）",
    "path": "含源文件名参数",
    "fpga": "含起始/结束帧号与帧间隔",
    "fpga_copy": "含副本号 + 起始/结束帧号与帧间隔",
}


def _pad_label(s: str, width: int = 10) -> str:
    """按显示宽度（中文计 2）左对齐，避免字段标签错列。"""
    w = sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)
    return s + " " * max(0, width - w)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x940")
        self.minsize(920, 800)

        self.log_q = queue.Queue()
        self.worker = None
        self.cancel_flag = threading.Event()
        self.last_outputs = []

        self._build_ui()
        self.after(120, self._drain_log)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.tab_gen = ttk.Frame(nb)
        self.tab_verify = ttk.Frame(nb)
        self.tab_cmd = ttk.Frame(nb)
        self.tab_rcs = ttk.Frame(nb)
        nb.add(self.tab_gen, text="  生成上注数据  ")
        nb.add(self.tab_verify, text="  校验已有上注包  ")
        nb.add(self.tab_cmd, text="  管理APP指令  ")
        nb.add(self.tab_rcs, text="  全部遥控指令  ")
        self._build_gen_tab()
        self._build_verify_tab()
        self._build_cmd_tab()
        self._build_rcs_tab()

        # 底部日志
        log_frame = ttk.LabelFrame(self, text="运行日志")
        log_frame.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log = tk.Text(log_frame, height=9, wrap="word", state="disabled",
                           font=("Consolas", 9), background="#fbfbfb", relief="flat")
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    def _build_gen_tab(self):
        f = self.tab_gen

        # 文件行
        io = ttk.LabelFrame(f, text="输入 / 输出")
        io.pack(fill="x", padx=10, pady=(10, 6))
        io.columnconfigure(1, weight=1)

        ttk.Label(io, text="源文件：").grid(row=0, column=0, sticky="e", padx=(8, 4), pady=6)
        self.var_input = tk.StringVar()
        ttk.Entry(io, textvariable=self.var_input).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Button(io, text="浏览…", width=8, command=self._pick_input).grid(row=0, column=2, padx=8)

        ttk.Label(io, text="输出文件：").grid(row=1, column=0, sticky="e", padx=(8, 4), pady=6)
        self.var_output = tk.StringVar()
        ttk.Entry(io, textvariable=self.var_output).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(io, text="另存为…", width=8, command=self._pick_output).grid(row=1, column=2, padx=8)

        ttk.Label(io, text="（输出留空则按所选级别自动命名并带包长，如 <源文件名>_frame986.bin / _tfdf980.bin / _tfdz977.bin / _pus964.bin / _data962.bin，与源文件同目录）",
                  foreground="#777").grid(row=2, column=1, sticky="w", pady=(0, 6))

        # 参数区
        p = ttk.LabelFrame(f, text="帧参数")
        p.pack(fill="x", padx=10, pady=6)
        for c in (1, 3, 5):
            p.columnconfigure(c, weight=1)

        ttk.Label(p, text="指令码：").grid(row=0, column=0, sticky="e", padx=(8, 4), pady=5)
        self.var_type = tk.StringVar(value="0x0E")
        self.cb_type = ttk.Combobox(p, textvariable=self.var_type, width=12,
                                    values=["0x0E", "0x1E"])
        self.cb_type.grid(row=0, column=1, sticky="w", pady=5)
        ttk.Label(p, text="0x0E 处理器上注 / 0x1E 高速Ku上注", foreground="#777").grid(
            row=0, column=2, sticky="w")

        ttk.Label(p, text="数据区长度N：").grid(row=0, column=4, sticky="e", padx=(16, 4), pady=5)
        self.var_dlen = tk.StringVar(value=str(PAYLOAD_SIZE))
        self.sp_dlen = ttk.Spinbox(p, from_=1, to=65535, textvariable=self.var_dlen, width=12)
        self.sp_dlen.grid(row=0, column=5, sticky="w", pady=5)

        ttk.Label(p, text="起始序号：").grid(row=1, column=0, sticky="e", padx=(8, 4), pady=5)
        self.var_seq = tk.StringVar(value="1")
        ttk.Spinbox(p, from_=0, to=65535, textvariable=self.var_seq, width=12).grid(
            row=1, column=1, sticky="w", pady=5)

        ttk.Label(p, text="序号字节序：").grid(row=2, column=0, sticky="e", padx=(8, 4), pady=5)
        self.var_seq_endian = tk.StringVar(value="big")
        ttk.Combobox(p, textvariable=self.var_seq_endian, width=10, state="readonly",
                     values=["big", "little"]).grid(row=2, column=1, sticky="w", pady=5)

        ttk.Label(p, text="长度字节序：").grid(row=2, column=2, sticky="e", padx=(16, 4), pady=5)
        self.var_len_endian = tk.StringVar(value="big")
        ttk.Combobox(p, textvariable=self.var_len_endian, width=10, state="readonly",
                     values=["big", "little"]).grid(row=2, column=3, sticky="w", pady=5)

        ttk.Label(p, text="填充字节：").grid(row=1, column=2, sticky="e", padx=(16, 4), pady=5)
        self.var_pad = tk.StringVar(value="0x55")
        ttk.Entry(p, textvariable=self.var_pad, width=12).grid(row=1, column=3, sticky="w", pady=5)

        ttk.Label(p, text="PUS 标识：").grid(row=1, column=4, sticky="e", padx=(16, 4), pady=5)
        self.var_pus = tk.StringVar(value="5F01")
        ttk.Entry(p, textvariable=self.var_pus, width=12).grid(row=1, column=5, sticky="w", pady=5)

        # 导头 / 差错控制
        h = ttk.LabelFrame(f, text="导头与差错控制（文档未定义，可保持默认）")
        h.pack(fill="x", padx=10, pady=6)
        h.columnconfigure(1, weight=1)
        h.columnconfigure(3, weight=1)

        ttk.Label(h, text="TFDF导头(3B)：").grid(row=0, column=0, sticky="e", padx=(8, 4), pady=5)
        self.var_tfdf = tk.StringVar(value="000000")
        self.e_tfdf = ttk.Entry(h, textvariable=self.var_tfdf, width=20)
        self.e_tfdf.grid(row=0, column=1, sticky="w", pady=5)

        self._scope_locked = True          # 默认 crc16-pus → 覆盖范围锁定为 pus
        ttk.Label(h, text="包差错控制：").grid(row=0, column=2, sticky="e", padx=(16, 4), pady=5)
        self.var_ecc = tk.StringVar(value="crc16-pus")
        self.cb_ecc = ttk.Combobox(h, textvariable=self.var_ecc, width=12, state="readonly",
                                   values=["crc16-pus", "crc16", "zeros", "sum16"])
        self.cb_ecc.bind("<<ComboboxSelected>>", self._on_ecc_change)
        self.cb_ecc.grid(row=0, column=3, sticky="w", pady=5)
        ttk.Label(h, text="crc16-pus=USLP CRC-16 仅覆盖PUS(默认)  crc16=覆盖TFDF整帧除ECC  zeros=0x0000  sum16=累加和",
                  foreground="#777").grid(row=0, column=4, columnspan=2, sticky="w")

        ttk.Label(h, text="TFDZ导头(11B)：").grid(row=1, column=0, sticky="e", padx=(8, 4), pady=5)
        self.var_tfdz = tk.StringVar(value="00" * TFDZ_HDR_LEN)
        self.e_tfdz = ttk.Entry(h, textvariable=self.var_tfdz, width=40, font=("Consolas", 9))
        self.e_tfdz.grid(row=1, column=1, sticky="ew", pady=5)

        ttk.Label(h, text="ECC覆盖范围：").grid(row=1, column=2, sticky="e", padx=(16, 4), pady=5)
        self.var_scope = tk.StringVar(value="pus")
        self.cb_scope = ttk.Combobox(h, textvariable=self.var_scope, width=12, state="disabled",
                                     values=["tfdf", "pus"])
        self.cb_scope.grid(row=1, column=3, sticky="w", pady=5)
        ttk.Label(h, text="tfdf=TFDF整帧除ECC  pus=仅PUS TC消息（crc16-pus 时锁定为 pus）", foreground="#777").grid(
            row=1, column=4, columnspan=2, sticky="w")

        # 输出格式
        fmt = ttk.LabelFrame(f, text="输出格式（N=数据区长度，默认 958）")
        fmt.pack(fill="x", padx=10, pady=6)
        fmt.columnconfigure(1, weight=1)
        self.var_fmt = tk.StringVar(value="frame")
        for r, (val, txt, hint) in enumerate([
            ("frame", "完整上注帧", "EB90+指令码+长度+TFDF+累加和，N+28 字节"),
            ("tfdf", "TFDF 帧", "TFDF导头+TFDZ+差错控制，N+22 字节"),
            ("tfdz", "TFDZ", "TFDZ导头+PUS TC消息+差错控制，N+19 字节"),
            ("pus", "PUS TC 消息", "5F01+序号+长度+数据，N+6 字节"),
            ("domain", "数据域", "序号+长度+数据，N+4 字节"),
            ("all", "全部五种", "同时输出五级包，文件名带包长"),
        ]):
            ttk.Radiobutton(fmt, text=txt, variable=self.var_fmt, value=val,
                            command=self._on_fmt_change).grid(
                row=r // 2, column=(r % 2) * 3, sticky="w", padx=(8, 4), pady=3)
            ttk.Label(fmt, foreground="#777", text=hint).grid(
                row=r // 2, column=(r % 2) * 3 + 1, columnspan=2, sticky="w")

        # 操作区
        op = ttk.Frame(f)
        op.pack(fill="x", padx=10, pady=(4, 8))
        self.btn_gen = ttk.Button(op, text="开始生成", width=14, command=self._start)
        self.btn_gen.pack(side="left")
        self.btn_cancel = ttk.Button(op, text="取消", width=8, state="disabled", command=self._cancel)
        self.btn_cancel.pack(side="left", padx=8)
        ttk.Button(op, text="打开输出目录", width=14, command=self._open_outdir).pack(side="left", padx=8)

        self.progress = ttk.Progressbar(op, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 8))
        self.var_status = tk.StringVar(value="就绪")
        ttk.Label(op, textvariable=self.var_status, width=22).pack(side="left")

    def _on_fmt_change(self):
        """按输出级别启用/禁用对应参数：仅 frame 有指令码与累加和；
        导头仅在含导头的级别（frame/tfdf/tfdz）有效；差错控制仅 frame/tfdf/tfdz 含有。"""
        lv = self.var_fmt.get()
        def en(w, on, ro=False):
            w.configure(state=("readonly" if on and ro else "normal" if on else "disabled"))
        en(self.cb_type, lv == "frame")
        en(self.e_tfdf, lv in ("frame", "tfdf"))
        en(self.e_tfdz, lv in ("frame", "tfdf", "tfdz"))
        en(self.cb_ecc, lv in ("frame", "tfdf", "tfdz"), ro=True)
        self._apply_scope_state()
        self.var_status.set("就绪" if lv == "frame" else f"输出级别：{lv}")

    def _on_ecc_change(self, _event=None):
        """选 crc16-pus 时覆盖范围锁定为 pus；切回其他模式时恢复可选（默认 tfdf）。"""
        if self.var_ecc.get() == "crc16-pus":
            self._scope_locked = True
            self.var_scope.set("pus")
        else:
            was = self._scope_locked
            self._scope_locked = False
            if was:
                self.var_scope.set("tfdf")
        self._apply_scope_state()

    def _apply_scope_state(self):
        lv = self.var_fmt.get()
        if self._scope_locked:
            self.cb_scope.configure(state="disabled")
        else:
            self.cb_scope.configure(state="readonly" if lv in ("frame", "tfdf", "tfdz") else "disabled")

    def _on_vecc_change(self, _event=None):
        """校验页：与生成页相同的联动规则。"""
        if self.var_vecc.get() == "crc16-pus":
            self._vscope_locked = True
            self.var_vscope.set("pus")
            self.cb_vscope.configure(state="disabled")
        else:
            was = self._vscope_locked
            self._vscope_locked = False
            if was:
                self.var_vscope.set("tfdf")
            self.cb_vscope.configure(state="readonly")

    def _build_verify_tab(self):
        f = self.tab_verify
        box = ttk.LabelFrame(f, text="选择已生成的上注包进行校验")
        box.pack(fill="x", padx=10, pady=(12, 8))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="上注包：").grid(row=0, column=0, sticky="e", padx=(8, 4), pady=8)
        self.var_vfile = tk.StringVar()
        ttk.Entry(box, textvariable=self.var_vfile).grid(row=0, column=1, sticky="ew", pady=8)
        ttk.Button(box, text="浏览…", width=8, command=self._pick_verify).grid(row=0, column=2, padx=8)

        ttk.Label(box, text="期望指令码：").grid(row=1, column=0, sticky="e", padx=(8, 4), pady=(0, 8))
        self.var_vtype = tk.StringVar(value="0x0E")
        ttk.Combobox(box, textvariable=self.var_vtype, width=10, values=["0x0E", "0x1E"]).grid(
            row=1, column=1, sticky="w", pady=(0, 8))

        ttk.Label(box, text="数据区长度N：").grid(row=1, column=2, sticky="e", padx=(24, 4), pady=(0, 8))
        self.var_vdlen = tk.StringVar(value=str(PAYLOAD_SIZE))
        ttk.Spinbox(box, from_=1, to=65507, textvariable=self.var_vdlen, width=10).grid(
            row=1, column=3, sticky="w", pady=(0, 8))

        ttk.Label(box, text="包级别：").grid(row=2, column=0, sticky="e", padx=(8, 4), pady=(0, 8))
        self.var_vlevel = tk.StringVar(value="auto")
        ttk.Combobox(box, textvariable=self.var_vlevel, width=12, state="readonly",
                     values=["auto", "frame", "tfdf", "tfdz", "pus", "domain"]).grid(
            row=2, column=1, sticky="w", pady=(0, 8))

        self._vscope_locked = True
        ttk.Label(box, text="差错控制：").grid(row=2, column=2, sticky="e", padx=(24, 4), pady=(0, 8))
        self.var_vecc = tk.StringVar(value="crc16-pus")
        self.cb_vecc = ttk.Combobox(box, textvariable=self.var_vecc, width=12, state="readonly",
                                    values=["crc16-pus", "crc16", "zeros", "sum16"])
        self.cb_vecc.bind("<<ComboboxSelected>>", self._on_vecc_change)
        self.cb_vecc.grid(row=2, column=3, sticky="w", pady=(0, 8))

        ttk.Label(box, text="ECC覆盖：").grid(row=3, column=0, sticky="e", padx=(8, 4), pady=(0, 10))
        self.var_vscope = tk.StringVar(value="pus")
        self.cb_vscope = ttk.Combobox(box, textvariable=self.var_vscope, width=10, state="disabled",
                                      values=["tfdf", "pus"])
        self.cb_vscope.grid(row=3, column=1, sticky="w", pady=(0, 10))

        ttk.Button(box, text="开始校验", width=14, command=self._do_verify).grid(
            row=3, column=2, columnspan=2, sticky="w", pady=(0, 10))

        self.verify_text = tk.Text(f, height=18, wrap="none", font=("Consolas", 10),
                                   background="#fbfbfb", relief="flat")
        self.verify_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # -------------------------------------------------------- 管理APP指令生成
    def _build_cmd_tab(self):
        f = self.tab_cmd
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, padx=10, pady=(8, 4))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # 左：指令树
        left = ttk.LabelFrame(body, text="指令列表（按功能分组）")
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        left.rowconfigure(0, weight=1)
        self.cmd_tree = ttk.Treeview(left, show="tree", selectmode="browse", height=19)
        sbl = ttk.Scrollbar(left, orient="vertical", command=self.cmd_tree.yview)
        self.cmd_tree.configure(yscrollcommand=sbl.set)
        self.cmd_tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sbl.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 6))

        groups = {}
        for c in COMMANDS:
            groups.setdefault(c.group, []).append(c)
        for g, items in groups.items():
            gid = "g:" + g
            self.cmd_tree.insert("", "end", iid=gid, text=g, open=True)
            for c in items:
                self.cmd_tree.insert(gid, "end", iid="c:" + c.cid,
                                     text=c.name.replace("管理APP-", ""))
        self.cmd_tree.bind("<<TreeviewSelect>>", self._cmd_on_select)

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        # 右上：指令信息
        info = ttk.LabelFrame(right, text="指令信息")
        info.grid(row=0, column=0, sticky="ew")
        info.columnconfigure(1, weight=1)
        self.var_cmd_name = tk.StringVar(value="← 请在左侧选择一条指令")
        self.var_cmd_desc = tk.StringVar(value="")
        self.var_cmd_kind = tk.StringVar(value="")
        ttk.Label(info, text="名称：").grid(row=0, column=0, sticky="e", padx=(8, 4), pady=(6, 2))
        ttk.Label(info, textvariable=self.var_cmd_name,
                  font=("Microsoft YaHei UI", 9, "bold"), foreground="#1a4b8c").grid(
            row=0, column=1, sticky="w", pady=(6, 2))
        ttk.Label(info, text="说明：").grid(row=1, column=0, sticky="e", padx=(8, 4), pady=2)
        ttk.Label(info, textvariable=self.var_cmd_desc, foreground="#444").grid(
            row=1, column=1, sticky="w", pady=2)
        ttk.Label(info, text="参数：").grid(row=2, column=0, sticky="e", padx=(8, 4), pady=(2, 6))
        ttk.Label(info, textvariable=self.var_cmd_kind, foreground="#777").grid(
            row=2, column=1, sticky="w", pady=(2, 6))

        # 右中：参数
        pf = ttk.LabelFrame(right, text="指令参数")
        pf.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.param_frame = pf
        pf.columnconfigure(1, weight=1)
        pf.columnconfigure(3, weight=1)

        self.var_path = tk.StringVar(value=SAMPLE_PATH)
        self.var_copy = tk.StringVar(value="1")
        self.var_start = tk.StringVar(value="1")
        self.var_end = tk.StringVar(value="1")
        self.var_ival = tk.StringVar(value="2")
        self.var_endian = tk.StringVar(value="big")
        self.var_trailing = tk.StringVar(value="")
        self.var_cs_scope = tk.StringVar(value="从 0x0F 起（不含帧头）")

        self.pw = {}
        w = self.pw
        w["path_lbl"] = ttk.Label(pf, text="源文件名：")
        w["path_lbl"].grid(row=0, column=0, sticky="e", padx=(8, 4), pady=5)
        w["path_ent"] = ttk.Entry(pf, textvariable=self.var_path, font=("Consolas", 9))
        w["path_ent"].grid(row=0, column=1, columnspan=3, sticky="ew", pady=5)
        w["path_btn"] = ttk.Button(pf, text="示例", width=5,
                                   command=lambda: self.var_path.set(SAMPLE_PATH))
        w["path_btn"].grid(row=0, column=4, sticky="w", padx=(4, 8), pady=5)

        w["endian_lbl"] = ttk.Label(pf, text="长度/帧号字节序：")
        w["endian_lbl"].grid(row=1, column=0, sticky="e", padx=(8, 4), pady=5)
        w["endian_cb"] = ttk.Combobox(pf, textvariable=self.var_endian, width=8,
                                      state="readonly", values=["big", "little"])
        w["endian_cb"].grid(row=1, column=1, sticky="w", pady=5)

        w["copy_lbl"] = ttk.Label(pf, text="副本号：")
        w["copy_lbl"].grid(row=1, column=2, sticky="e", padx=(16, 4), pady=5)
        w["copy"] = ttk.Spinbox(pf, from_=0, to=255, textvariable=self.var_copy, width=8)
        w["copy"].grid(row=1, column=3, sticky="w", pady=5)

        w["start_lbl"] = ttk.Label(pf, text="起始帧号：")
        w["start_lbl"].grid(row=2, column=0, sticky="e", padx=(8, 4), pady=5)
        w["start"] = ttk.Spinbox(pf, from_=0, to=65535, textvariable=self.var_start, width=10)
        w["start"].grid(row=2, column=1, sticky="w", pady=5)

        w["end_lbl"] = ttk.Label(pf, text="结束帧号：")
        w["end_lbl"].grid(row=2, column=2, sticky="e", padx=(16, 4), pady=5)
        w["end"] = ttk.Spinbox(pf, from_=0, to=65535, textvariable=self.var_end, width=10)
        w["end"].grid(row=2, column=3, sticky="w", pady=5)

        w["ival_lbl"] = ttk.Label(pf, text="帧间隔：")
        w["ival_lbl"].grid(row=3, column=0, sticky="e", padx=(8, 4), pady=5)
        w["ival"] = ttk.Spinbox(pf, from_=0, to=65535, textvariable=self.var_ival, width=10)
        w["ival"].grid(row=3, column=1, sticky="w", pady=5)

        w["trail_lbl"] = ttk.Label(pf, text="参数末尾附加字：")
        w["trail_lbl"].grid(row=3, column=2, sticky="e", padx=(16, 4), pady=5)
        w["trail"] = ttk.Entry(pf, textvariable=self.var_trailing, width=12,
                               font=("Consolas", 9))
        w["trail"].grid(row=3, column=3, sticky="w", pady=5)

        w["cs_lbl"] = ttk.Label(pf, text="累加和范围：")
        w["cs_lbl"].grid(row=4, column=0, sticky="e", padx=(8, 4), pady=5)
        w["cs_cb"] = ttk.Combobox(pf, textvariable=self.var_cs_scope, width=22,
                                  state="readonly",
                                  values=["从 0x0F 起（不含帧头）", "从 0xEB 起（含帧头）"])
        w["cs_cb"].grid(row=4, column=1, columnspan=2, sticky="w", pady=5)

        ttk.Label(pf, text="帧结构：EB 90 | 0F | n(2B) | 设备号 05 05 | 功能码 2B | "
                           "功能参数 | 累加和；n = 参数 + 4，整帧 n+6 字节",
                  foreground="#777").grid(row=5, column=0, columnspan=5, sticky="w",
                                          padx=8, pady=(2, 0))
        ttk.Label(pf, text="累加和 = 类型字至参数末字节之和的低 8 位（含帧头可切换）；"
                           "多字节字段一律大端。",
                  foreground="#777").grid(row=6, column=0, columnspan=5, sticky="w",
                                          padx=8, pady=(0, 6))

        # 按钮
        op = ttk.Frame(right)
        op.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(op, text="生成指令", width=12, command=self._cmd_generate).pack(side="left")
        ttk.Button(op, text="复制 HEX", width=10, command=self._cmd_copy).pack(side="left", padx=8)
        ttk.Button(op, text="保存报文…", width=12, command=self._cmd_save).pack(side="left")
        self.var_cmd_status = tk.StringVar(value="")
        ttk.Label(op, textvariable=self.var_cmd_status, foreground="#1a7f37").pack(side="left", padx=12)

        # 输出
        out = ttk.LabelFrame(right, text="生成的指令报文")
        out.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        right.rowconfigure(3, weight=1)
        self.cmd_text = tk.Text(out, height=8, wrap="word", font=("Consolas", 10),
                                background="#fbfbfb", relief="flat")
        sbo = ttk.Scrollbar(out, command=self.cmd_text.yview)
        self.cmd_text.configure(yscrollcommand=sbo.set)
        sbo.pack(side="right", fill="y", pady=6, padx=(0, 6))
        self.cmd_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.cmd_bytes = b""
        self.cur_cmd = None

        # 默认选中第一条
        first = COMMANDS[0].cid
        self.cmd_tree.selection_set("c:" + first)
        self.cmd_tree.see("c:" + first)

    def _cmd_show(self, keys, show):
        for k in keys:
            w = self.pw[k]
            if show:
                w.grid()
            else:
                w.grid_remove()

    def _cmd_on_select(self, _evt=None):
        sel = self.cmd_tree.selection()
        if not sel or not sel[0].startswith("c:"):
            return
        cmd = BY_ID[sel[0][2:]]
        self.cur_cmd = cmd
        self.var_cmd_name.set(cmd.name)
        self.var_cmd_desc.set(cmd.desc)
        self.var_cmd_kind.set(KIND_LABEL[cmd.kind])

        self._cmd_show(["path_lbl", "path_ent", "path_btn"], cmd.kind == "path")
        self._cmd_show(["endian_lbl", "endian_cb"],
                       cmd.kind in ("path", "fpga", "fpga_copy"))
        self._cmd_show(["copy_lbl", "copy"], cmd.kind == "fpga_copy")
        self._cmd_show(["start_lbl", "start", "end_lbl", "end", "ival_lbl", "ival"],
                       cmd.kind in ("fpga", "fpga_copy"))
        self.cmd_text.delete("1.0", "end")
        self.cmd_bytes = b""
        self.var_cmd_status.set("")

        code = " ".join(f"{b:02X}" for b in cmd.code)
        fixed_n = MIN_LEN + len(cmd.params)
        hint = (f"帧头：{HEADER.hex(' ').upper()}   类型字：{TYPE_CODE:02X}   "
                f"设备号/功能码：{code}\n")
        if cmd.params:
            hint += f"固定功能参数：{' '.join(f'{b:02X}' for b in cmd.params)}\n"
        hint += (f"无参数时整帧 {fixed_n + 6} 字节（n={fixed_n}）；"
                 f"实际长度随参数自动计算")
        if cmd.doc_cs >= 0:
            hint += f"\n表内累加和：{cmd.doc_cs:02X}"
        self.cmd_text.insert("end", hint + "\n")

    def _cmd_generate(self):
        if not self.cur_cmd:
            messagebox.showinfo("提示", "请先在左侧选择一条指令。")
            return
        cmd = self.cur_cmd
        try:
            trail_txt = self.var_trailing.get().strip().replace(" ", "")
            trailing = bytes.fromhex(trail_txt) if trail_txt else b""
            data = cmd_encode(
                cmd.cid,
                path=self.var_path.get().strip() or None,
                copy_no=int(self.var_copy.get(), 0) if cmd.kind == "fpga_copy" else None,
                start_frame=int(self.var_start.get(), 0) if cmd.kind in ("fpga", "fpga_copy") else None,
                end_frame=int(self.var_end.get(), 0) if cmd.kind in ("fpga", "fpga_copy") else None,
                interval=int(self.var_ival.get(), 0) if cmd.kind in ("fpga", "fpga_copy") else None,
                endian=self.var_endian.get(),
                include_header=self.var_cs_scope.get().startswith("从 0xEB"),
                trailing=trailing,
            )
            if cmd.kind == "path":
                self.var_path.get().strip().encode("ascii")
        except UnicodeEncodeError:
            messagebox.showerror("参数错误", "源文件名只能包含 ASCII 字符（板卡上的 Linux 路径）。")
            return
        except ValueError as e:
            messagebox.showerror("参数错误", f"参数有误：{e}")
            return

        self.cmd_bytes = data
        n = int.from_bytes(data[3:5], "big")
        hex_str = " ".join(f"{b:02X}" for b in data)
        if len(data) > 16:
            hex_str = "\n       ".join(
                " ".join(f"{b:02X}" for b in data[i:i + 16])
                for i in range(0, len(data), 16))
        lines = [f"{cmd.name}",
                 f"整帧长度：{len(data)} 字节（n={n}，总长=n+6）"
                 f"   累加和范围：{self.var_cs_scope.get()}"]
        lines.append("HEX  ：" + hex_str)
        lines.append("")
        lines.append("字段分解：")
        for name, seg, note in cmd_split(data, cmd):
            hexs = " ".join(f"{b:02X}" for b in seg)
            extra = f"  ({note})" if note else ""
            if name == "功能参数" and cmd.kind == "path":
                try:
                    ln = int.from_bytes(seg[2:4], "big")
                    extra += f"  源长度={ln}，源文件名={seg[4:4 + ln].decode('ascii', 'replace')}"
                except Exception:
                    pass
            lines.append(f"  {_pad_label(name, 14)}: {hexs}{extra}")
        self.cmd_text.delete("1.0", "end")
        self.cmd_text.insert("end", "\n".join(lines) + "\n")
        self.var_cmd_status.set("已生成")
        self._log(f"[指令] {cmd.name}  {len(data)} 字节  " +
                  " ".join(f"{b:02X}" for b in data))

    def _cmd_copy(self):
        if not self.cmd_bytes:
            messagebox.showinfo("提示", "请先生成指令。")
            return
        self.clipboard_clear()
        self.clipboard_append(" ".join(f"{b:02X}" for b in self.cmd_bytes))
        self.var_cmd_status.set("HEX 已复制到剪贴板")

    def _cmd_save(self):
        if not self.cmd_bytes:
            messagebox.showinfo("提示", "请先生成指令。")
            return
        path = filedialog.asksaveasfilename(
            title="保存指令报文", defaultextension=".bin",
            initialfile=(self.cur_cmd.cid if self.cur_cmd else "cmd") + ".bin",
            filetypes=[("二进制文件", "*.bin"), ("所有文件", "*.*")])
        if not path:
            return
        with open(path, "wb") as fp:
            fp.write(self.cmd_bytes)
        self.var_cmd_status.set("已保存")
        self._log(f"[指令] 已保存 {path}（{len(self.cmd_bytes)} 字节）")

    # ------------------------------------------------------ 全部遥控指令（包表）
    def _build_rcs_tab(self):
        f = self.tab_rcs
        top = ttk.LabelFrame(f, text="遥控包表工作簿")
        top.pack(fill="x", padx=10, pady=(8, 4))
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="工作簿：").grid(row=0, column=0, sticky="e", padx=(8, 4), pady=6)
        self.var_xlsx = tk.StringVar(value=RCS_XLSX_DEFAULT)
        ttk.Entry(top, textvariable=self.var_xlsx, font=("Consolas", 9)).grid(
            row=0, column=1, sticky="ew", pady=6)
        ttk.Button(top, text="浏览…", width=7, command=self._rcs_pick_xlsx).grid(
            row=0, column=2, padx=6)
        ttk.Button(top, text="加载/刷新", width=10, command=self._rcs_load).grid(
            row=0, column=3, padx=(0, 8))
        self.var_rcs_status = tk.StringVar(value="点击「加载/刷新」读取工作簿")
        ttk.Label(top, textvariable=self.var_rcs_status, foreground="#1a7f37").grid(
            row=1, column=1, columnspan=3, sticky="w", pady=(0, 6))

        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 4))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(body, text="指令列表（工作表 → 指令）")
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        left.rowconfigure(0, weight=1)
        self.rcs_tree = ttk.Treeview(left, show="tree", selectmode="browse", height=17)
        sbl = ttk.Scrollbar(left, orient="vertical", command=self.rcs_tree.yview)
        self.rcs_tree.configure(yscrollcommand=sbl.set)
        self.rcs_tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sbl.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 6))
        self.rcs_tree.bind("<<TreeviewSelect>>", self._rcs_on_select)
        self.rcs_catalog = []
        self.rcs_report = []

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        info = ttk.LabelFrame(right, text="指令信息")
        info.grid(row=0, column=0, sticky="ew")
        info.columnconfigure(1, weight=1)
        self.var_rcs_name = tk.StringVar(value="← 先加载工作簿并选择指令")
        self.var_rcs_meta = tk.StringVar(value="")
        self.var_rcs_note = tk.StringVar(value="")
        ttk.Label(info, text="名称：").grid(row=0, column=0, sticky="e", padx=(8, 4), pady=(6, 2))
        ttk.Label(info, textvariable=self.var_rcs_name,
                  font=("Microsoft YaHei UI", 9, "bold"), foreground="#1a4b8c").grid(
            row=0, column=1, sticky="w", pady=(6, 2))
        ttk.Label(info, text="结构：").grid(row=1, column=0, sticky="e", padx=(8, 4), pady=2)
        ttk.Label(info, textvariable=self.var_rcs_meta, foreground="#444").grid(
            row=1, column=1, sticky="w", pady=2)
        ttk.Label(info, text="提示：").grid(row=2, column=0, sticky="e", padx=(8, 4), pady=(2, 6))
        ttk.Label(info, textvariable=self.var_rcs_note, foreground="#a15c00").grid(
            row=2, column=1, sticky="w", pady=(2, 6))

        pf = ttk.LabelFrame(right, text="指令参数（按模板自动生成）")
        pf.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.rcs_param_inner = ttk.Frame(pf)
        self.rcs_param_inner.pack(fill="x", padx=8, pady=6)
        self.rcs_vars = []

        ttk.Label(right, text="帧结构：EB 90 | 类型字 | 有效数据长度 n(2B) | 设备号 | 功能码 | "
                              "参数 | 累加和；长度与累加和自动计算",
                  foreground="#777").grid(row=2, column=0, sticky="w", padx=6, pady=(4, 0))

        op = ttk.Frame(right)
        op.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(op, text="生成指令", width=12, command=self._rcs_generate).pack(side="left")
        ttk.Button(op, text="复制 HEX", width=10, command=self._rcs_copy).pack(side="left", padx=8)
        ttk.Button(op, text="保存报文…", width=12, command=self._rcs_save).pack(side="left")
        self.var_rcs_gen_status = tk.StringVar(value="")
        ttk.Label(op, textvariable=self.var_rcs_gen_status, foreground="#1a7f37").pack(
            side="left", padx=12)

        out = ttk.LabelFrame(right, text="生成的指令报文")
        out.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        self.rcs_text = tk.Text(out, height=9, wrap="word", font=("Consolas", 10),
                                background="#fbfbfb", relief="flat")
        sbo = ttk.Scrollbar(out, command=self.rcs_text.yview)
        self.rcs_text.configure(yscrollcommand=sbo.set)
        sbo.pack(side="right", fill="y", pady=6, padx=(0, 6))
        self.rcs_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.rcs_bytes = b""
        self.cur_rcs = None

    def _rcs_pick_xlsx(self):
        path = filedialog.askopenfilename(title="选择遥控包表工作簿",
                                          filetypes=[("Excel 工作簿", "*.xlsx"), ("所有文件", "*.*")])
        if path:
            self.var_xlsx.set(path)

    def _rcs_load(self):
        path = self.var_xlsx.get().strip()
        if not os.path.isfile(path):
            messagebox.showwarning("提示", "工作簿路径不存在。")
            return
        try:
            cat, rep = rcs_table.load_catalog(path)
        except Exception:
            messagebox.showerror("加载失败", traceback.format_exc())
            return
        self.rcs_catalog, self.rcs_report = cat, rep
        self.rcs_tree.delete(*self.rcs_tree.get_children())
        sheets = {}
        for idx, c in enumerate(cat):
            sheets.setdefault(c.sheet, []).append(idx)
        for sheet, idxs in sheets.items():
            sid = "s:" + sheet
            self.rcs_tree.insert("", "end", iid=sid,
                                 text=f"{sheet}（{len(idxs)}）", open=(sheet == list(sheets)[0]))
            for i in idxs:
                self.rcs_tree.insert(sid, "end", iid=f"r:{i}", text=cat[i].name)
        ok = sum(1 for c in cat if c.example_ok)
        self.var_rcs_status.set(f"共 {len(cat)} 条指令，示例回验/校验通过 {ok} 条，"
                                f"待确认 {len(rep)} 条")
        self._log(f"[遥控包表] 已加载 {path}")
        self._log(f"[遥控包表] 指令 {len(cat)} 条，通过 {ok} 条，待确认 {len(rep)} 条")
        for item in rep[:12]:
            self._log("   " + " / ".join(str(x) for x in item))
        if cat:
            first = "r:0"
            self.rcs_tree.selection_set(first)
            self.rcs_tree.see(first)

    def _rcs_on_select(self, _evt=None):
        sel = self.rcs_tree.selection()
        if not sel or not sel[0].startswith("r:"):
            return
        cmd = self.rcs_catalog[int(sel[0][2:])]
        self.cur_rcs = cmd
        self.var_rcs_name.set(cmd.name)
        n_fields = len(cmd.fields)
        self.var_rcs_meta.set(f"{cmd.sheet} 第 {cmd.row} 行 · 类型字 0x{cmd.type_code:02X} · "
                              f"字段 {n_fields} 个 · 累计长 {sum((f.size or 0) for f in cmd.fields)}B")
        notes = [r[3] for r in self.rcs_report if r[0] == cmd.sheet and r[1] == cmd.row]
        self.var_rcs_note.set("；".join(notes) if notes else
                              ("示例已回验一致" if cmd.example_ok else "模板本身即实码"))

        for w in self.rcs_param_inner.winfo_children():
            w.destroy()
        self.rcs_vars = []
        if not cmd.fields:
            ttk.Label(self.rcs_param_inner, text="该指令无参数（固定报文）",
                      foreground="#777").grid(row=0, column=0, sticky="w")
        for i, fd in enumerate(cmd.fields):
            val = cmd.defaults.get(fd.name, 0 if fd.kind == "num" else "")
            if fd.kind == "num":
                width = 2 * (fd.size or 1)
                text = f"0x{int(val):0{width}X}" if isinstance(val, int) else str(val)
            else:
                text = str(val)
            var = tk.StringVar(value=text)
            ttk.Label(self.rcs_param_inner, text=fd.name + "：").grid(
                row=i, column=0, sticky="e", padx=(4, 4), pady=3)
            ent = ttk.Entry(self.rcs_param_inner, textvariable=var, font=("Consolas", 9))
            ent.grid(row=i, column=1, sticky="ew", padx=(0, 8), pady=3)
            self.rcs_param_inner.columnconfigure(1, weight=1)
            unit = f"{fd.size}B" if fd.size else "变长(自动填长度)"
            ttk.Label(self.rcs_param_inner, text=unit, foreground="#777").grid(
                row=i, column=2, sticky="w", padx=(0, 8))
            self.rcs_vars.append((fd, var))
        self.rcs_text.delete("1.0", "end")
        self.rcs_bytes = b""
        self.var_rcs_gen_status.set("")
        if cmd.example:
            self.rcs_text.insert("end", "表内示例：" +
                                 " ".join(f"{b:02X}" for b in cmd.example) + "\n")

    def _rcs_generate(self):
        if not self.cur_rcs:
            messagebox.showinfo("提示", "请先加载工作簿并选择指令。")
            return
        cmd = self.cur_rcs
        values = {}
        try:
            for fd, var in self.rcs_vars:
                raw = var.get().strip()
                if fd.kind == "num":
                    values[fd.name] = int(raw, 0) if raw else 0
                else:
                    values[fd.name] = raw
            data = rcs_table.assemble(cmd, values)
        except Exception as e:                            # noqa: BLE001
            messagebox.showerror("参数错误", str(e))
            return

        self.rcs_bytes = data
        # 同步长度字段的显示值
        for fd, var in self.rcs_vars:
            if fd.is_length:
                for tf, tv in self.rcs_vars:
                    if tf.kind != "num" and tf.pair >= 0 and cmd.fields[tf.pair] is fd:
                        raw = tv.get()
                        try:
                            if tf.kind == "ascii":
                                blen = len(raw.encode("ascii"))
                            else:
                                blen = len(bytes.fromhex(raw.replace(" ", "")))
                            var.set(f"0x{blen:0{2 * (fd.size or 1)}X}")
                        except Exception:
                            pass
        n = int.from_bytes(data[3:5], "big")
        lines = [f"{cmd.sheet} / {cmd.name}",
                 f"整帧 {len(data)} 字节（n={n}），类型字 0x{cmd.type_code:02X}",
                 "HEX  ：" + " ".join(f"{b:02X}" for b in data)]
        if len(data) > 24:
            lines[-1] = "HEX  ：" + "\n       ".join(
                " ".join(f"{b:02X}" for b in data[i:i + 20]) for i in range(0, len(data), 20))
        lines.append("")
        lines.append("字段值：")
        for fd, var in self.rcs_vars:
            lines.append(f"  {_pad_label(fd.name, 14)}: {var.get()}")
        self.rcs_text.delete("1.0", "end")
        self.rcs_text.insert("end", "\n".join(lines) + "\n")
        self.var_rcs_gen_status.set("已生成")
        self._log(f"[遥控包] {cmd.name}  {len(data)} 字节  " +
                  " ".join(f"{b:02X}" for b in data))

    def _rcs_copy(self):
        if not self.rcs_bytes:
            messagebox.showinfo("提示", "请先生成指令。")
            return
        self.clipboard_clear()
        self.clipboard_append(" ".join(f"{b:02X}" for b in self.rcs_bytes))
        self.var_rcs_gen_status.set("HEX 已复制")

    def _rcs_save(self):
        if not self.rcs_bytes:
            messagebox.showinfo("提示", "请先生成指令。")
            return
        name = (self.cur_rcs.name.replace("/", "_") if self.cur_rcs else "cmd")
        path = filedialog.asksaveasfilename(title="保存指令报文", defaultextension=".bin",
                                            initialfile=name + ".bin",
                                            filetypes=[("二进制文件", "*.bin"), ("所有文件", "*.*")])
        if not path:
            return
        with open(path, "wb") as fp:
            fp.write(self.rcs_bytes)
        self.var_rcs_gen_status.set("已保存")
        self._log(f"[遥控包] 已保存 {path}")

    # --------------------------------------------------------------- 文件选择
    def _pick_input(self):
        path = filedialog.askopenfilename(title="选择要上注的二进制文件",
                                          filetypes=[("二进制文件", "*.bin"), ("所有文件", "*.*")])
        if path:
            self.var_input.set(path)
            self.var_output.set("")
            self._log(f"已选择源文件：{path}  （{os.path.getsize(path)} 字节）")

    def _pick_output(self):
        init = self.var_input.get()
        default = (os.path.splitext(os.path.basename(init))[0] + "_frame986.bin") if init else "frame986.bin"
        path = filedialog.asksaveasfilename(title="保存上注数据",
                                            defaultextension=".bin",
                                            initialfile=default,
                                            filetypes=[("二进制文件", "*.bin"), ("所有文件", "*.*")])
        if path:
            self.var_output.set(path)

    def _pick_verify(self):
        path = filedialog.askopenfilename(title="选择上注包",
                                          filetypes=[("二进制文件", "*.bin"), ("所有文件", "*.*")])
        if path:
            self.var_vfile.set(path)

    def _open_outdir(self):
        path = self.var_output.get().strip() or self.var_input.get().strip()
        d = os.path.dirname(os.path.abspath(path)) if path else HERE
        try:
            os.startfile(d)
        except Exception:
            self._log(f"无法打开目录：{d}")

    # ------------------------------------------------------------------ 日志
    def _log(self, msg: str):
        self.log_q.put(msg)

    def _drain_log(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", msg + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(120, self._drain_log)

    # ------------------------------------------------------------------ 生成
    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        src = self.var_input.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showwarning("提示", "请先选择有效的源文件。")
            return

        try:
            cfg = {
                "type_code": int(self.var_type.get(), 0) & 0xFF,
                "start_seq": int(self.var_seq.get(), 0),
                "seq_endian": self.var_seq_endian.get(),
                "len_endian": self.var_len_endian.get(),
                "tfdf_hdr": parse_hex_bytes(self.var_tfdf.get(), 3, "TFDF导头"),
                "tfdz_hdr": parse_hex_bytes(self.var_tfdz.get(), TFDZ_HDR_LEN, "TFDZ导头"),
                "pus_id": parse_hex_bytes(self.var_pus.get(), 2, "PUS标识"),
                "ecc": self.var_ecc.get(),
                "ecc_scope": self.var_scope.get(),
                "pad": int(self.var_pad.get(), 0) & 0xFF,
                "data_len": int(self.var_dlen.get(), 0),
                "level": self.var_fmt.get(),
            }
            if not 1 <= cfg["data_len"] <= 65535 - 28:
                raise ValueError(f"数据区长度 N 需在 1~65507 之间")
        except SystemExit as e:
            messagebox.showerror("参数错误", str(e))
            return
        except ValueError as e:
            messagebox.showerror("参数错误", f"数值格式不正确：{e}")
            return

        n = cfg["data_len"]
        lv = cfg["level"]
        base = os.path.splitext(src)[0]
        if lv == "all":
            out = self.var_output.get().strip() or (base + "_packs.bin")
        else:
            out = self.var_output.get().strip() or level_filename(src, lv, n)

        self.btn_gen.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.cancel_flag.clear()
        self.progress.configure(value=0)
        self.var_status.set("生成中…")
        self.last_outputs = [out]

        self.worker = threading.Thread(target=self._run, args=(src, out, cfg), daemon=True)
        self.worker.start()

    def _cancel(self):
        self.cancel_flag.set()
        self._log("已请求取消，将在当前分块结束后停止。")

    def _run(self, src, out, cfg):
        try:
            n = cfg["data_len"]
            lv = cfg["level"]
            levels = list(ALL_LEVELS) if lv == "all" else [lv]
            if lv == "all":
                outs = {l: level_filename(out, l, n) for l in levels}
            else:
                outs = {lv: out}
            sz = sizes(n)

            total = os.path.getsize(src)
            frames_total = (total + n - 1) // n
            self._log("=" * 62)
            self._log(f"源文件   : {src}  ({total} 字节)")
            for l in levels:
                self._log(f"输出文件 : {outs[l]}  [{LEVEL_NAME.get(l, l)}，{sz[l]} 字节/包]")
            self._log(f"参数     : 数据区N={n} 起始序号={cfg['start_seq']} "
                      f"序号序={cfg['seq_endian']} 长度序={cfg['len_endian']}")
            if lv == "frame":
                self._log(f"           指令码=0x{cfg['type_code']:02X}")
            if lv in ("frame", "tfdf", "tfdz"):
                self._log(f"           差错控制={cfg['ecc']}（覆盖: "
                          f"{'TFDF整帧除ECC' if cfg['ecc_scope'] == 'tfdf' else '仅PUS TC消息'}）")
            self._log(f"预计包数 : {frames_total} 包")

            tmps = {l: p + ".part" for l, p in outs.items()}
            seq = cfg["start_seq"]
            done = 0
            handles = {l: open(p, "wb") for l, p in tmps.items()}
            try:
                with open(src, "rb") as fin:
                    while True:
                        if self.cancel_flag.is_set():
                            break
                        block = fin.read(max(PROGRESS_CHUNK // n * n, n))
                        if not block:
                            break
                        cnt = (len(block) + n - 1) // n
                        for i in range(cnt):
                            chunk = block[i * n:(i + 1) * n]
                            if not chunk:
                                break
                            units = build_units(seq, chunk, cfg)
                            for l, fh in handles.items():
                                fh.write(units[l])
                            seq = (seq + 1) & 0xFFFF
                            done += 1
                        pct = done * 100 / frames_total if frames_total else 100
                        self._ui_progress(pct, f"生成中 {done}/{frames_total} 包")
            finally:
                for fh in handles.values():
                    fh.close()

            if self.cancel_flag.is_set():
                for p in tmps.values():
                    if os.path.exists(p):
                        os.remove(p)
                self._log("已取消，临时文件已清理。")
                self._ui_done("已取消")
                return

            for l, p in tmps.items():
                os.replace(p, outs[l])
            self._log(f"生成完成 : {done} 包")
            self._ui_progress(100, "生成完成")

            # 自检
            self._log("开始自检…")
            ok = True
            for l, p in outs.items():
                ok &= verify_pkg(p, l, data_len=n, pus_id=cfg["pus_id"],
                                 type_code=cfg["type_code"], endian=cfg["seq_endian"],
                                 ecc=cfg["ecc"] if l in ("frame", "tfdf", "tfdz") else None,
                                 ecc_scope=cfg["ecc_scope"])
            self._log("自检通过 ✓" if ok else "自检失败 ✗，请检查参数")
            self._ui_done("完成，自检通过" if ok else "完成，但自检失败")
        except Exception:
            self._log("发生异常：\n" + traceback.format_exc())
            self._ui_done("失败")

    def _ui_progress(self, pct, status):
        self.after(0, lambda: (self.progress.configure(value=pct), self.var_status.set(status)))

    def _ui_done(self, status):
        def _f():
            self.var_status.set(status)
            self.btn_gen.configure(state="normal")
            self.btn_cancel.configure(state="disabled")
        self.after(0, _f)

    # ------------------------------------------------------------------ 校验
    def _do_verify(self):
        path = self.var_vfile.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("提示", "请先选择上注包文件。")
            return
        tc = int(self.var_vtype.get(), 0) & 0xFF
        n = int(self.var_vdlen.get(), 0)
        size = os.path.getsize(path)

        self.verify_text.delete("1.0", "end")
        self.verify_text.insert("end", f"文件：{path}\n大小：{size} 字节\n\n")
        self.update_idletasks()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                if self.var_vlevel.get() == "auto":
                    level = detect_level(path, n)
                    if level is None:
                        ok = False
                        print(f"[失败] 文件大小 {size} 与 N={n} 的各级别包长均不匹配")
                    else:
                        print(f"[自动识别] 包级别: {LEVEL_NAME.get(level, level)}")
                        ok = verify_pkg(path, level, data_len=n, pus_id=parse_hex_bytes(
                                            self.var_pus.get(), 2, "PUS标识"),
                                        type_code=tc, endian="big",
                                        ecc=self.var_vecc.get(), ecc_scope=self.var_vscope.get())
                else:
                    ok = verify_pkg(path, self.var_vlevel.get(), data_len=n,
                                    pus_id=parse_hex_bytes(self.var_pus.get(), 2, "PUS标识"),
                                    type_code=tc, endian="big",
                                    ecc=self.var_vecc.get(), ecc_scope=self.var_vscope.get())
            self.verify_text.insert("end", buf.getvalue())
            self.verify_text.insert("end", f"\n结论：{'校验通过 ✓' if ok else '校验失败 ✗'}\n")
        except Exception:
            self.verify_text.insert("end", "异常：\n" + traceback.format_exc())


if __name__ == "__main__":
    app = App()
    app.mainloop()
