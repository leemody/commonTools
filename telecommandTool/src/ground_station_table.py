"""Parse and frame the ground-station parameter table."""

from __future__ import annotations

import posixpath
import re
import zipfile
from io import BytesIO
from typing import Dict, List, Tuple
from xml.etree import ElementTree

import low_speed_telecommand_frame_generator as low


MAX_STATIONS = 255
MAX_COORDINATE = 7_000_000
DEFAULT_COMMAND_CODE = 0x5F01
DEFAULT_PARAMETER_LIMIT = 450
MAX_PARAMETER_LIMIT = 452


def _column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Z]+", cell_reference.upper())
    if not letters:
        raise ValueError("Excel工作表包含无效的单元格地址")
    result = 0
    for character in letters.group(0):
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = []
    for item in root:
        if _local_name(item.tag) != "si":
            continue
        values.append("".join(node.text or "" for node in item.iter() if _local_name(node.tag) == "t"))
    return values


def _worksheet_path(archive: zipfile.ZipFile) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    first_sheet = next((node for node in workbook.iter() if _local_name(node.tag) == "sheet"), None)
    if first_sheet is None:
        raise ValueError("Excel文件中没有工作表")
    relationship_id = next((value for key, value in first_sheet.attrib.items() if key.endswith("}id")), None)
    if not relationship_id:
        raise ValueError("Excel首个工作表缺少关系定义")
    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = None
    for relationship in relationships:
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib.get("Target")
            break
    if not target:
        raise ValueError("Excel首个工作表关系无效")
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("xl", target))


def _cell_value(cell: ElementTree.Element, shared_strings: List[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter() if _local_name(node.tag) == "t").strip()
    value_node = next((node for node in cell if _local_name(node.tag) == "v"), None)
    if value_node is None or value_node.text is None:
        return ""
    value = value_node.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (IndexError, ValueError) as exc:
            raise ValueError("Excel文件包含无效的共享字符串索引") from exc
    return value


def _xlsx_rows(source: bytes) -> List[List[str]]:
    try:
        with zipfile.ZipFile(BytesIO(source)) as archive:
            if len(archive.infolist()) > 1000 or sum(item.file_size for item in archive.infolist()) > 16 * 1024 * 1024:
                raise ValueError("Excel展开后的数据不能超过16 MiB")
            shared_strings = _read_shared_strings(archive)
            worksheet_path = _worksheet_path(archive)
            root = ElementTree.fromstring(archive.read(worksheet_path))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError("无法读取Excel文件，请使用有效的.xlsx文件") from exc

    rows = []
    for row_node in root.iter():
        if _local_name(row_node.tag) != "row":
            continue
        cells: Dict[int, str] = {}
        for cell in row_node:
            if _local_name(cell.tag) != "c":
                continue
            reference = cell.attrib.get("r", "")
            cells[_column_index(reference)] = _cell_value(cell, shared_strings)
        if cells:
            rows.append([cells.get(index, "") for index in range(max(cells) + 1)])
    return rows


def _integer(value, name: str, row_number: int) -> int:
    text = str(value).strip()
    if not text:
        raise ValueError(f"第{row_number}行缺少{name}")
    try:
        numeric = float(text)
    except ValueError as exc:
        raise ValueError(f"第{row_number}行{name}必须是整数") from exc
    if not numeric.is_integer():
        raise ValueError(f"第{row_number}行{name}必须是整数")
    return int(numeric)


def _looks_like_header(row: List[str]) -> bool:
    normalized = [value.strip().lower().replace(" ", "").replace("_", "").replace("-", "") for value in row]
    station_names = {"station", "stationid", "stationnumber", "stationno", "groundstationid", "id", "站点", "站点编号", "地面站", "地面站编号", "编号"}
    x_names = {"x", "stationx", "stationnumberx", "groundstationx", "x坐标", "坐标x"}
    y_names = {"y", "stationy", "stationnumbery", "groundstationy", "y坐标", "坐标y"}
    z_names = {"z", "stationz", "stationnumberz", "groundstationz", "z坐标", "坐标z"}
    return (any(value in station_names for value in normalized)
            and any(value in x_names for value in normalized)
            and any(value in y_names for value in normalized)
            and any(value in z_names for value in normalized))


def parse_station_rows(rows: List[List[str]]) -> List[Dict[str, int]]:
    if not rows:
        raise ValueError("Excel中没有地面站数据")
    header = rows[0] if _looks_like_header(rows[0]) else None
    if header is None:
        column_map = (0, 1, 2, 3)
        data_rows = rows
        first_row_number = 1
    else:
        normalized = [value.strip().lower().replace(" ", "").replace("_", "").replace("-", "") for value in header]
        aliases = (
            {"station", "stationid", "stationnumber", "stationno", "groundstationid", "id", "站点", "站点编号", "地面站", "地面站编号", "编号"},
            {"x", "stationx", "stationnumberx", "groundstationx", "x坐标", "坐标x"},
            {"y", "stationy", "stationnumbery", "groundstationy", "y坐标", "坐标y"},
            {"z", "stationz", "stationnumberz", "groundstationz", "z坐标", "坐标z"},
        )
        column_map = tuple(next(i for i, value in enumerate(normalized) if value in names) for names in aliases)
        data_rows = rows[1:]
        first_row_number = 2

    stations = []
    for row_number, row in enumerate(data_rows, first_row_number):
        fields = [row[index].strip() if index < len(row) else "" for index in column_map]
        if not any(fields):
            continue
        station_id, x, y, z = (
            _integer(fields[0], "地面站编号", row_number),
            _integer(fields[1], "X坐标", row_number),
            _integer(fields[2], "Y坐标", row_number),
            _integer(fields[3], "Z坐标", row_number),
        )
        stations.append({"station": station_id, "x": x, "y": y, "z": z})
        if len(stations) > MAX_STATIONS:
            raise ValueError("地面站数量不能超过255个")
    if not stations:
        raise ValueError("Excel中没有有效的地面站数据")
    return stations


def parse_station_xlsx(source: bytes) -> List[Dict[str, int]]:
    return parse_station_rows(_xlsx_rows(source))


def encode_station_table(stations: List[dict]) -> bytes:
    if not isinstance(stations, list) or not 1 <= len(stations) <= MAX_STATIONS:
        raise ValueError("地面站数量须为1..255")
    encoded_rows = []
    for index, station in enumerate(stations, 1):
        if not isinstance(station, dict):
            raise ValueError(f"第{index}个地面站数据格式错误")
        station_id = _integer(station.get("station", ""), "地面站编号", index)
        if not 0 <= station_id <= 254:
            raise ValueError(f"第{index}个地面站编号须为0..254")
        record = bytearray((station_id,))
        for key, label in (("x", "X坐标"), ("y", "Y坐标"), ("z", "Z坐标")):
            coordinate = _integer(station.get(key, ""), label, index)
            if not -MAX_COORDINATE <= coordinate <= MAX_COORDINATE:
                raise ValueError(f"第{index}个地面站{label}须在-7000000..7000000范围内")
            record.extend(coordinate.to_bytes(3, "big", signed=True))
        encoded_rows.append(bytes(record))

    table_size = 4 + sum(map(len, encoded_rows))
    table = bytearray((len(encoded_rows),))
    table.extend(table_size.to_bytes(3, "big"))
    for record in encoded_rows:
        table.extend(record)
    return bytes(table)


def build_ground_station_frames(
    stations: List[dict], *, command_code: int = DEFAULT_COMMAND_CODE,
    scid: int = 0xFF01, vcf_count: int = 0, pid: int = 2, pcat: int = 3,
    service_type: int = 2, service_subtype: int = 2,
    parameter_limit: int = DEFAULT_PARAMETER_LIMIT,
) -> Tuple[bytes, List[bytes]]:
    if not 0 <= command_code <= 0xFFFF:
        raise ValueError("指令码须为0..0xFFFF")
    if not 1 <= parameter_limit <= MAX_PARAMETER_LIMIT:
        raise ValueError("每帧参数长度须为1..452字节")
    table = encode_station_table(stations)
    frames = []
    for offset in range(0, len(table), parameter_limit):
        frames.append(low.build_low_speed_frame(
            scid=scid, vcf_count=(vcf_count + len(frames)) & 0xFF,
            pid=pid, pcat=pcat, service_type=service_type,
            service_subtype=service_subtype, command_code=command_code,
            parameters=table[offset:offset + parameter_limit],
        ))
    return table, frames
