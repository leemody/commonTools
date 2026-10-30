'''Create a two-sheet XLSX workbook for ordinary file-upload frames.'''
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def _column_name(number):
    name=''
    while number:
        number,remainder=divmod(number-1,26)
        name=chr(65+remainder)+name
    return name


def _worksheet_xml(rows):
    parts=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for row_number,row in enumerate(rows,1):
        parts.append(f'<row r="{row_number}">')
        for column,value in enumerate(row,1):
            cell_ref=f'{_column_name(column)}{row_number}'
            if isinstance(value,int):
                parts.append(f'<c r="{cell_ref}" t="n"><v>{value}</v></c>')
            else:
                parts.append(f'<c r="{cell_ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>')
        parts.append('</row>')
    parts.append('</sheetData></worksheet>')
    return ''.join(parts).encode('utf-8')


def _data_domain(frame):
    if len(frame)<58 or int.from_bytes(frame[4:6],'big')+1!=len(frame):
        raise ValueError('Invalid low-speed frame in Excel export')
    packet_start=25
    packet_end=packet_start+int.from_bytes(frame[packet_start+4:packet_start+6],'big')+7
    if packet_end>len(frame)-18 or packet_end<38:
        raise ValueError('PUS packet length is invalid in Excel export')
    app_start=packet_start+11
    return frame[app_start:packet_end-2]


def create_low_upload_workbook(frame_hex_list):
    if not isinstance(frame_hex_list,list) or not frame_hex_list:
        raise ValueError('At least one frame is required for Excel export')
    if len(frame_hex_list)>100000:
        raise ValueError('Too many frames for Excel export')
    full_rows=[['\u5e27\u5e8f\u53f7','\u6574\u5e27 HEX']]
    data_rows=[['\u5e27\u5e8f\u53f7','\u6570\u636e\u57df HEX']]
    for index,frame_hex in enumerate(frame_hex_list,1):
        if not isinstance(frame_hex,str):
            raise ValueError('Frame HEX must be text')
        try:
            frame=bytes.fromhex(frame_hex)
        except ValueError as exc:
            raise ValueError(f'Frame {index} contains invalid HEX') from exc
        data=_data_domain(frame)
        full_rows.append([index,frame.hex(' ').upper()])
        data_rows.append([index,data.hex(' ').upper()])
    sheet_full='\u6574\u5e27\u6570\u636e'
    sheet_data='\u6570\u636e\u57df'
    workbook=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        '<sheet name="'+sheet_full+'" sheetId="1" r:id="rId1"/>'
        '<sheet name="'+sheet_data+'" sheetId="2" r:id="rId2"/>'
        '</sheets></workbook>')
    content_types=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
    root_rels=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    book_rels=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml',content_types)
        archive.writestr('_rels/.rels',root_rels)
        archive.writestr('xl/workbook.xml',workbook.encode('utf-8'))
        archive.writestr('xl/_rels/workbook.xml.rels',book_rels)
        archive.writestr('xl/worksheets/sheet1.xml',_worksheet_xml(full_rows))
        archive.writestr('xl/worksheets/sheet2.xml',_worksheet_xml(data_rows))
    return output.getvalue()


def create_high_upload_workbook(frame_hex_list):
    """Create a three-sheet workbook for high-speed upload frames."""
    if not isinstance(frame_hex_list, list) or not frame_hex_list:
        raise ValueError('At least one frame is required for Excel export')
    if len(frame_hex_list) > 100000:
        raise ValueError('Too many frames for Excel export')
    full_rows = [['\u5e27\u5e8f\u53f7', '\u6574\u5e27 HEX']]
    tfdf_rows = [['\u5e27\u5e8f\u53f7', '\u6709\u6548 TFDF HEX']]
    wrapped_rows = [['\u5e27\u5e8f\u53f7', '422 HEX (EB900E)']]
    for index, frame_hex in enumerate(frame_hex_list, 1):
        if not isinstance(frame_hex, str):
            raise ValueError('Frame HEX must be text')
        try:
            frame = bytes.fromhex(frame_hex)
        except ValueError as exc:
            raise ValueError(f'Frame {index} contains invalid HEX') from exc
        if len(frame) != 1020 or int.from_bytes(frame[4:6], 'big') + 1 != len(frame):
            raise ValueError(f'Frame {index} is not a valid 1020-byte high-speed frame')
        # High-speed upload uses 14 security bytes, then the 3-byte TFDF header.
        tfdf_header = 8 + 14
        data_start = tfdf_header + 3
        valid_length = int.from_bytes(frame[tfdf_header + 1:tfdf_header + 3], 'big') + 1
        if valid_length < 13 or data_start + valid_length > len(frame) - 18:
            raise ValueError(f'Frame {index} has an invalid TFDF valid-data pointer')
        tfdf_header_bytes = frame[tfdf_header:tfdf_header + 3]
        tfdf = frame[data_start:data_start + valid_length]
        if index == len(frame_hex_list):
            # Preserve the final frame's full TFDZ, including AA fill bytes.
            tfdf = frame[data_start:len(frame) - 18]
        tfdf_with_header = tfdf_header_bytes + tfdf
        # 422 checksum covers type (0x0E), length, TFDF header, and selected TFDZ; EB90 is excluded.
        packet = bytearray((0xEB, 0x90, 0x0E)) + len(tfdf_with_header).to_bytes(2, 'big') + tfdf_with_header
        packet.append(sum(packet[2:]) & 0xFF)
        full_rows.append([index, frame.hex(' ').upper()])
        tfdf_rows.append([index, tfdf.hex(' ').upper()])
        wrapped_rows.append([index, packet.hex(' ').upper()])
    sheets = [('\u6574\u5e27\u6570\u636e', full_rows), ('TFDF\u6709\u6548\u6570\u636e', tfdf_rows), ('422\u6570\u636e', wrapped_rows)]
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        + ''.join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i, (name, _) in enumerate(sheets, 1))
        + '</sheets></workbook>')
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, 4))
        + '</Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    book_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, 4))
        + '</Relationships>')
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', root_rels)
        archive.writestr('xl/workbook.xml', workbook.encode('utf-8'))
        archive.writestr('xl/_rels/workbook.xml.rels', book_rels)
        for index, (_, rows) in enumerate(sheets, 1):
            archive.writestr(f'xl/worksheets/sheet{index}.xml', _worksheet_xml(rows))
    return output.getvalue()


def create_high_upload_422_binary(frame_hex_list):
    """Concatenate one 422 packet for each valid high-speed upload frame."""
    if not isinstance(frame_hex_list, list) or not frame_hex_list:
        raise ValueError('At least one frame is required for 422 BIN export')
    if len(frame_hex_list) > 100000:
        raise ValueError('Too many frames for 422 BIN export')
    packets = []
    for index, frame_hex in enumerate(frame_hex_list, 1):
        if not isinstance(frame_hex, str):
            raise ValueError('Frame HEX must be text')
        try:
            frame = bytes.fromhex(frame_hex)
        except ValueError as exc:
            raise ValueError(f'Frame {index} contains invalid HEX') from exc
        if len(frame) != 1020 or int.from_bytes(frame[4:6], 'big') + 1 != len(frame):
            raise ValueError(f'Frame {index} is not a valid 1020-byte high-speed frame')
        tfdf_header = 22
        data_start = tfdf_header + 3
        valid_length = int.from_bytes(frame[tfdf_header + 1:tfdf_header + 3], 'big') + 1
        if valid_length < 13 or data_start + valid_length > len(frame) - 18:
            raise ValueError(f'Frame {index} has an invalid TFDF valid-data pointer')
        payload_end = data_start + valid_length
        if index == len(frame_hex_list):
            # Preserve the final frame's full TFDZ, including AA fill bytes.
            payload_end = len(frame) - 18
        payload = frame[tfdf_header:payload_end]
        packet = bytearray((0xEB, 0x90, 0x0E)) + len(payload).to_bytes(2, 'big') + payload
        packet.append(sum(packet[2:]) & 0xFF)
        packets.append(bytes(packet))
    return b''.join(packets)
