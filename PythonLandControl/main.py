#!/usr/bin/env python3

import argparse
import socket
from pathlib import Path

from excel_parser import parse_excel_to_task_plan
from task_data_model import DEFAULT_APID, build_tc_frame, format_hex


def parse_hex_int(value: str) -> int:
    return int(value, 16) if value.lower().startswith("0x") else int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and send a task-plan TC Frame from Excel.")
    parser.add_argument("--excel", default="commands.xlsx", help="Excel file path, default: commands.xlsx")
    parser.add_argument("--sheet", default=None, help="Worksheet name, default: first worksheet")
    parser.add_argument("--host", default="127.0.0.1", help="UDP destination host, default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=55042, help="UDP destination port, default: 55042")
    parser.add_argument("--plan-id", type=parse_hex_int, default=100, help="Task plan ID, default: 100")
    parser.add_argument("--format-ver", type=parse_hex_int, default=1, help="Task plan format version, default: 1")
    parser.add_argument("--apid", type=parse_hex_int, default=DEFAULT_APID, help="EPDU APID, default: 0x43")
    parser.add_argument("--dry-run", action="store_true", help="Print frame bytes without sending UDP")
    args = parser.parse_args()

    excel_path = Path(args.excel)
    if not excel_path.is_absolute():
        excel_path = Path(__file__).resolve().parent / excel_path

    task_plan = parse_excel_to_task_plan(str(excel_path),
                                         sheet_name=args.sheet,
                                         format_ver=args.format_ver,
                                         plan_id=args.plan_id)
    frame = build_tc_frame(task_plan, apid=args.apid)

    print(f"TaskPlan plan_id={task_plan.plan_id} step_count={task_plan.step_count}")
    for index, step in enumerate(task_plan.steps, start=1):
        print(f"[{index:03d}] device=0x{step.device_id:02X} cmd=0x{step.cmd_id:04X} arg_len={step.arg_len}")

    print(f"\nTC Frame bytes ({len(frame)} bytes):")
    print(format_hex(frame))

    if args.dry_run:
        return 0

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sent = sock.sendto(frame, (args.host, args.port))

    print(f"\nsent {sent} bytes to {args.host}:{args.port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
