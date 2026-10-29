#!/usr/bin/env python3
"""本地遥控帧生成页面：python src/web_server.py"""

import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import low_speed_telecommand_frame_generator as low
import time_schedule_telecommand_frame_generator as schedule
import direct_command_frame_generator as direct
import high_speed_frame_generator as high
import high_speed_idle_frame_generator as idle


RESOURCE_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
PAGE = RESOURCE_ROOT / "frontend" / "index.html"


def number(data, key, default=None):
    value = data.get(key, default)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{key}必须是整数")
    try:
        return int(value, 0) if isinstance(value, str) else value
    except ValueError as exc:
        raise ValueError(f"{key}必须是十进制或0x开头的十六进制整数") from exc


def hex_bytes(data, key):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{key}必须是十六进制字节串")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{key}必须是完整的十六进制字节串") from exc


def ids(data):
    values = data.get("sub_schedule_ids", [])
    if not isinstance(values, list):
        raise ValueError("子调度表ID必须是列表")
    return [number({"id": value}, "id") for value in values]


def generate(data):
    if not isinstance(data, dict):
        raise ValueError("请求内容必须是对象")
    kind = data.get("kind")
    if kind == "high_idle":
        return idle.build_high_speed_idle_frame(scid=number(data, "scid", "0xFF01"),
                                                vcf_count=number(data, "vcf", 0))
    if kind == "high":
        vcid = number(data, "vcid", 10)
        if vcid is None:
            vcid = 10
        return high.build_high_speed_frame(
            scid=number(data, "scid", "0xFF01"), vcf_count=number(data, "vcf", 0),
            pid=number(data, "pid", 2), pcat=number(data, "pcat", 3),
            map_id=number(data, "map_id", 14), vcid=vcid,
            sequence_count=number(data, "sequence_count", 0),
            sequence_flags=number(data, "sequence_flags", 3), app_data=hex_bytes(data, "app_data"),
        )
    if kind == "direct":
        return direct.build_direct_command_frame(
            scid=number(data, "scid", "0xFF01"),
            vcf_count=number(data, "vcf", 0),
            pid=number(data, "pid", 2),
            pcat=number(data, "pcat", 3),
            command_code=hex_bytes(data, "command_code"),
        )
    if kind == "low":
        return low.build_low_speed_frame(
            scid=number(data, "scid", "0xFF01"),
            vcf_count=number(data, "vcf", 0),
            pid=number(data, "pid", 2),
            pcat=number(data, "pcat", 3),
            service_type=number(data, "service_type", 2),
            service_subtype=number(data, "service_subtype", 2),
            command_code=number(data, "command_code", "0x5001"),
            parameters=hex_bytes(data, "parameters"),
        )
    if kind != "schedule":
        raise ValueError("未知帧类型")
    common = dict(
        scid=number(data, "scid", "0xFF01"),
        vcf_count=number(data, "vcf", 0),
        pid=number(data, "pid", 1),
        pcat=number(data, "pcat", 3),
    )
    command = data.get("command")
    if command in ("enable", "disable", "reset"):
        return getattr(schedule, f"build_{command}_frame")(**common)
    if command == "insert":
        raw = data.get("activities", [])
        if not isinstance(raw, list):
            raise ValueError("活动必须是列表")
        activities = []
        for index, item in enumerate(raw, 1):
            if not isinstance(item, dict):
                raise ValueError(f"第{index}条活动格式错误")
            activities.append(schedule.ScheduledActivity(
                release_time=number(item, "release_time"),
                pid=number(item, "pid"),
                pcat=number(item, "pcat"),
                service_type=number(item, "service_type"),
                service_subtype=number(item, "service_subtype"),
                sequence_count=number(item, "sequence_count", 0),
                app_data=hex_bytes(item, "app_data"),
            ))
        return schedule.build_insert_frame(
            activities, sub_schedule_id=number(data, "sub_schedule_id", 1), **common
        )
    if command in ("delete", "shift"):
        options = dict(
            time_type=number(data, "time_type", 0),
            time_tag1=number(data, "time_tag1"),
            time_tag2=number(data, "time_tag2"),
            sub_schedule_ids=ids(data),
            **common,
        )
        if command == "shift":
            options["time_offset"] = number(data, "time_offset", 0)
        return getattr(schedule, f"build_{command}_frame")(**options)
    if command == "summary":
        return schedule.build_summary_frame(sub_schedule_ids=ids(data), **common)
    raise ValueError("未知调度命令")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        resources = {
            "/": (PAGE, "text/html; charset=utf-8"),
            "/image.png": (PAGE.with_name("image.png"), "image/png"),
        }
        resource = resources.get(self.path)
        if resource is None:
            self.send_error(404)
            return
        path, content_type = resource
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/generate":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 65536:
                raise ValueError("请求大小应在1..65536字节范围内")
            data = json.loads(self.rfile.read(size))
            frame = generate(data)
            body = json.dumps({"size": len(frame), "hex": frame.hex(" ").upper()}, ensure_ascii=False).encode()
            status = 200
        except (ValueError, TypeError, OverflowError, json.JSONDecodeError) as exc:
            body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode()
            status = 400
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    address = ("127.0.0.1", 8000)
    url = f"http://{address[0]}:{address[1]}"
    server = ThreadingHTTPServer(address, Handler)
    print(f"打开 {url}；关闭此窗口可停止服务。")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    server.serve_forever()
