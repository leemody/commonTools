import openpyxl
from typing import List, Dict, Optional, Any
from task_data_model import Step, TaskPlanData
from collections import OrderedDict


class CommandExcelParser:
    """
    命令 Excel 文件解析器
    用于解析 commands.xlsx 文件，表头格式：
    - 指令ID(Hex)
    - 指令名称
    - 参数排序
    - 参数(类型 / 描述)
    - 数据类型
    - 编码定义
    - 赋值
    """
    
    def __init__(self, file_path: str):
        """
        初始化解析器
        
        参数:
            file_path: Excel 文件路径
        """
        self.file_path = file_path
        self.workbook = None
        self.worksheet = None
    
    def load(self, sheet_name: Optional[str] = None):
        """
        加载 Excel 文件
        
        参数:
            sheet_name: 工作表名称，默认为第一个工作表（Sheet1）
        """
        self.workbook = openpyxl.load_workbook(self.file_path)
        
        if sheet_name:
            if sheet_name in self.workbook.sheetnames:
                self.worksheet = self.workbook[sheet_name]
            else:
                raise ValueError(f"工作表 '{sheet_name}' 不存在，可用工作表: {self.workbook.sheetnames}")
        else:
            # 默认使用第一个工作表（通常是 Sheet1）
            self.worksheet = self.workbook.worksheets[0]
            print(f"使用第一个工作表: {self.worksheet.title}")
    
    def parse_to_list(self, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        解析 Excel 文件为字典列表
        
        返回的每个字典包含以下键：
        - command_id_hex: 指令ID（十六进制字符串）
        - command_name: 指令名称
        - param_order: 参数排序
        - param_description: 参数描述
        - data_type: 数据类型
        - encoding_definition: 编码定义
        - value: 赋值
        
        参数:
            sheet_name: 工作表名称，默认为第一个工作表
            
        返回:
            字典列表
        """
        self.load(sheet_name)
        
        rows = list(self.worksheet.iter_rows(values_only=True))
        
        if len(rows) < 2:
            return []
        
        # 获取表头并标准化
        headers = [str(h).strip() if h is not None else '' for h in rows[0]]
        
        # 查找各列的索引
        column_mapping = {}
        for idx, header in enumerate(headers):
            if '指令ID' in header or '指令ID(Hex)' in header:
                column_mapping['command_id_hex'] = idx
            elif '指令名称' in header:
                column_mapping['command_name'] = idx
            elif '参数排序' in header:
                column_mapping['param_order'] = idx
            elif '参数' in header and ('类型' in header or '描述' in header):
                column_mapping['param_description'] = idx
            elif '数据类型' in header:
                column_mapping['data_type'] = idx
            elif '编码定义' in header:
                column_mapping['encoding_definition'] = idx
            elif header == '赋值':
                column_mapping['value'] = idx
        
        # 解析每一行数据
        result_list = []
        for row_num, row in enumerate(rows[1:], start=2):
            # 跳过空行
            if not any(cell is not None for cell in row):
                continue
            
            try:
                item = {}
                
                # 提取各字段
                if 'command_id_hex' in column_mapping:
                    val = row[column_mapping['command_id_hex']]
                    item['command_id_hex'] = str(val).strip() if val is not None else ''
                
                if 'command_name' in column_mapping:
                    val = row[column_mapping['command_name']]
                    item['command_name'] = str(val).strip() if val is not None else ''
                
                if 'param_order' in column_mapping:
                    val = row[column_mapping['param_order']]
                    item['param_order'] = int(val) if val is not None and val != '' else 0
                
                if 'param_description' in column_mapping:
                    val = row[column_mapping['param_description']]
                    item['param_description'] = str(val).strip() if val is not None else ''
                
                if 'data_type' in column_mapping:
                    val = row[column_mapping['data_type']]
                    item['data_type'] = str(val).strip() if val is not None else ''
                
                if 'encoding_definition' in column_mapping:
                    val = row[column_mapping['encoding_definition']]
                    item['encoding_definition'] = str(val).strip() if val is not None else ''
                
                if 'value' in column_mapping:
                    val = row[column_mapping['value']]
                    item['value'] = val
                
                result_list.append(item)
                
            except Exception as e:
                print(f"警告: 第 {row_num} 行解析失败: {e}，已跳过")
                continue
        
        return result_list
    
    def close(self):
        """关闭工作簿"""
        if self.workbook:
            self.workbook.close()


def parse_commands_to_list(file_path: str = 'commands.xlsx', 
                           sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    便捷函数：解析 commands.xlsx 文件为字典列表
    
    参数:
        file_path: Excel 文件路径，默认为 'commands.xlsx'
        sheet_name: 工作表名称，默认为第一个工作表
        
    返回:
        字典列表，每个字典包含：
        - command_id_hex: 指令ID（十六进制字符串）
        - command_name: 指令名称
        - param_order: 参数排序
        - param_description: 参数描述
        - data_type: 数据类型
        - encoding_definition: 编码定义
        - value: 赋值
    """
    parser = CommandExcelParser(file_path)
    try:
        return parser.parse_to_list(sheet_name)
    finally:
        parser.close()


def _convert_value_to_bytes(value: Any, data_type: str) -> bytes:
    """
    根据数据类型将值转换为 bytes
    
    参数:
        value: 赋值的原始值
        data_type: 数据类型字符串
        
    返回:
        bytes 数据
    """
    if value is None or value == '':
        return b''
    
    try:
        # 如果是十六进制字符串
        if isinstance(value, str):
            value = value.strip()
            
            # 判断是否为十六进制格式
            if value.startswith('0x') or value.startswith('0X'):
                hex_str = value[2:]
                return bytes.fromhex(hex_str)
            elif all(c in '0123456789abcdefABCDEF' for c in value) and len(value) % 2 == 0:
                # 纯十六进制字符串
                return bytes.fromhex(value)
        
        # 根据数据类型转换
        if data_type in ['uint8', 'byte', 'uint8_t']:
            return bytes([int(value)])
        elif data_type in ['uint16', 'word', 'uint16_t']:
            val = int(value)
            return val.to_bytes(2, byteorder='little')
        elif data_type in ['uint32', 'dword', 'uint32_t']:
            val = int(value)
            return val.to_bytes(4, byteorder='little')
        elif data_type in ['int8', 'int8_t']:
            return int(value).to_bytes(1, byteorder='little', signed=True)
        elif data_type in ['int16', 'int16_t']:
            return int(value).to_bytes(2, byteorder='little', signed=True)
        elif data_type in ['int32', 'int32_t']:
            return int(value).to_bytes(4, byteorder='little', signed=True)
        elif data_type in ['float', 'float32']:
            import struct
            return struct.pack('<f', float(value))
        elif data_type in ['double', 'float64']:
            import struct
            return struct.pack('<d', float(value))
        elif data_type in ['string', 'str', 'char[]']:
            if isinstance(value, str):
                return value.encode('utf-8')
            else:
                return str(value).encode('utf-8')
        else:
            # 默认尝试转换为字符串
            if isinstance(value, str):
                return value.encode('utf-8')
            else:
                return str(value).encode('utf-8')
                
    except Exception as e:
        print(f"警告: 值转换失败 [value={value}, type={data_type}]: {e}")
        return b''


def convert_commands_to_steps(commands_list: List[Dict[str, Any]]) -> List[Step]:
    """
    将解析后的命令列表转换为 Step 对象列表
    
    规则：
    - command_id_hex 相同的归为同一个 Step
    - 每个 Step 内的 value 按照 param_order 升序排列
    - 将所有 value 按顺序拼接为 args
    
    参数:
        commands_list: 从 parse_commands_to_list 返回的字典列表
        
    返回:
        Step 对象列表
    """
    # 按 command_id_hex 分组
    grouped_commands = OrderedDict()
    
    for cmd in commands_list:
        cmd_id_hex = cmd.get('command_id_hex', '').strip()
        if not cmd_id_hex:
            print(f"警告: 跳过空指令ID的记录: {cmd}")
            continue
        
        # 标准化指令ID（去除 0x 前缀，统一大写）
        cmd_id_hex = cmd_id_hex.replace('0x', '').replace('0X', '').upper()
        
        if cmd_id_hex not in grouped_commands:
            grouped_commands[cmd_id_hex] = []
        
        grouped_commands[cmd_id_hex].append(cmd)
    
    # 转换为 Step 列表
    steps = []
    for cmd_id_hex, cmds in grouped_commands.items():
        try:
            # 解析指令ID
            cmd_id = int(cmd_id_hex, 16)
            
            # 按 param_order 升序排序
            sorted_cmds = sorted(cmds, key=lambda x: x.get('param_order', 0))
            
            # 拼接所有 value 为 args
            args = b''
            for cmd in sorted_cmds:
                value = cmd.get('value')
                data_type = cmd.get('data_type', '').lower()
                
                if value is None or value == '':
                    continue
                
                # 根据数据类型转换 value 为 bytes
                arg_bytes = _convert_value_to_bytes(value, data_type)
                args += arg_bytes
            
            # 创建 Step（unit_id 默认为 0，可根据需要调整）
            step = Step(unit_id=0, cmd_id=cmd_id, args=args)
            steps.append(step)
            
        except Exception as e:
            print(f"警告: 转换指令 {cmd_id_hex} 失败: {e}")
            continue
    
    return steps


def parse_excel_to_task_plan(file_path: str = 'commands.xlsx',
                             sheet_name: Optional[str] = None,
                             format_ver: int = 1,
                             plan_id: int = 0) -> TaskPlanData:
    """
    便捷函数：直接从 Excel 文件解析为 TaskPlanData 对象
    
    参数:
        file_path: Excel 文件路径，默认为 'commands.xlsx'
        sheet_name: 工作表名称，默认为第一个工作表
        format_ver: 格式版本号
        plan_id: 计划ID
        
    返回:
        TaskPlanData 对象
    """
    # 第一步：解析 Excel 为字典列表
    commands_list = parse_commands_to_list(file_path, sheet_name)
    
    # 第二步：转换为 Step 列表
    steps = convert_commands_to_steps(commands_list)
    
    # 第三步：创建 TaskPlanData
    task_plan = TaskPlanData(format_ver=format_ver, plan_id=plan_id, steps=steps)
    
    return task_plan


# 使用示例
if __name__ == "__main__":
    excel_file = 'commands.xlsx'
    
    try:
        # 方式1: 解析为字典列表
        print("=" * 80)
        print("方式1: 解析为字典列表")
        print("=" * 80)
        commands_list = parse_commands_to_list(excel_file)
        print(f"解析到 {len(commands_list)} 条命令记录:\n")
        
        for i, cmd in enumerate(commands_list, 1):
            print(f"记录 {i}:")
            for key, value in cmd.items():
                print(f"  {key}: {value}")
            print()
        
        # 方式2: 转换为 Step 列表
        print("=" * 80)
        print("方式2: 转换为 Step 列表（按 command_id_hex 分组）")
        print("=" * 80)
        steps = convert_commands_to_steps(commands_list)
        print(f"转换后得到 {len(steps)} 个步骤:\n")
        
        for i, step in enumerate(steps, 1):
            print(f"步骤 {i}: {step}")
            if step.args:
                print(f"  参数(hex): {step.args.hex()}")
                print(f"  参数长度: {len(step.args)} 字节")
            print()
        
        # 方式3: 直接解析为 TaskPlanData
        print("=" * 80)
        print("方式3: 直接解析为 TaskPlanData")
        print("=" * 80)
        task_plan = parse_excel_to_task_plan(excel_file, format_ver=1, plan_id=1001)
        print(f"任务计划: {task_plan}\n")
        
        # 序列化测试
        data_bytes = task_plan.to_bytes()
        print(f"序列化后字节长度: {len(data_bytes)}")
        print(f"序列化后字节数据: {data_bytes.hex()}\n")
        
        # 反序列化测试
        restored_plan, size = TaskPlanData.from_bytes(data_bytes)
        print(f"反序列化结果: {restored_plan}")
            
    except FileNotFoundError:
        print(f"错误: 文件 '{excel_file}' 不存在")
    except ImportError as e:
        print(f"错误: {e}")
        print("请安装 openpyxl: pip install openpyxl")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
