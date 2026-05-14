import struct
from typing import List


class Step:
    """
    步骤数据结构
    {
        uint8  unit_id;      // 单元ID (1字节)
        uint16 cmd_id;       // 命令ID (2字节)
        uint16 arg_len;      // 参数长度 (2字节)
        uint8  args[arg_len]; // 参数数据 (可变长度)
    }
    """
    
    # Step 头部格式：unit_id(1) + cmd_id(2) + arg_len(2)
    HEADER_FORMAT = '<BHH'  # 小端字节序
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    
    def __init__(self, unit_id: int = 0, cmd_id: int = 0, args: bytes = b''):
        self.unit_id = unit_id
        self.cmd_id = cmd_id
        self.args = args
        self.arg_len = len(args)
    
    def to_bytes(self) -> bytes:
        """将 Step 序列化为字节流"""
        header = struct.pack(
            self.HEADER_FORMAT,
            self.unit_id,
            self.cmd_id,
            self.arg_len
        )
        return header + self.args

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0) -> tuple:
        """
        从字节流中解析 Step
        返回: (Step对象, 占用的总字节数)
        """
        # 解包头部
        unit_id, cmd_id, arg_len = struct.unpack_from(cls.HEADER_FORMAT, data, offset)
        
        # 提取参数数据
        args_start = offset + cls.HEADER_SIZE
        args = data[args_start:args_start + arg_len]
        
        step = cls(unit_id=unit_id, cmd_id=cmd_id, args=args)
        total_size = cls.HEADER_SIZE + arg_len
        
        return step, total_size
    
    def __repr__(self):
        return f"Step(unit_id={self.unit_id}, cmd_id={self.cmd_id}, arg_len={self.arg_len})"


class TaskPlanData:
    """
    任务计划数据结构
    {
        uint8  format_ver;           // 格式版本 (1字节)
        uint16 plan_id;              // 计划ID (2字节)
        uint8  step_count;           // 步骤数量 (1字节)
        Step steps[step_count];      // 步骤数组 (可变长度)
    }
    """
    
    # TaskPlanData 头部格式：format_ver(1) + plan_id(2) + step_count(1)
    HEADER_FORMAT = '<B H B'  # 小端字节序
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    
    def __init__(self, format_ver: int = 0, plan_id: int = 0, steps: List[Step] = None):
        self.format_ver = format_ver
        self.plan_id = plan_id
        self.steps = steps if steps is not None else []
        self.step_count = len(self.steps)
    
    def to_bytes(self) -> bytes:
        """将 TaskPlanData 序列化为字节流"""
        # 更新步骤数量
        self.step_count = len(self.steps)
        
        # 打包头部
        header = struct.pack(
            self.HEADER_FORMAT,
            self.format_ver,
            self.plan_id,
            self.step_count
        )
        
        # 打包所有步骤
        steps_data = b''.join(step.to_bytes() for step in self.steps)
        
        return header + steps_data
    
    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0) -> tuple:
        """
        从字节流中解析 TaskPlanData
        返回: (TaskPlanData对象, 占用的总字节数)
        """
        # 解包头部
        format_ver, plan_id, step_count = struct.unpack_from(cls.HEADER_FORMAT, data, offset)
        
        # 解析步骤数组
        steps = []
        current_offset = offset + cls.HEADER_SIZE
        
        for _ in range(step_count):
            step, step_size = Step.from_bytes(data, current_offset)
            steps.append(step)
            current_offset += step_size
        
        task_plan = cls(format_ver=format_ver, plan_id=plan_id, steps=steps)
        total_size = cls.HEADER_SIZE + (current_offset - (offset + cls.HEADER_SIZE))
        
        return task_plan, total_size
    
    def add_step(self, unit_id: int, cmd_id: int, args: bytes = b''):
        """添加一个步骤"""
        step = Step(unit_id=unit_id, cmd_id=cmd_id, args=args)
        self.steps.append(step)
        self.step_count = len(self.steps)
    
    def clear_steps(self):
        """清空所有步骤"""
        self.steps.clear()
        self.step_count = 0
    
    def __repr__(self):
        return f"TaskPlanData(format_ver={self.format_ver}, plan_id={self.plan_id}, step_count={self.step_count}, steps={self.steps})"


# 使用示例
if __name__ == "__main__":
    # 创建任务计划
    plan = TaskPlanData(format_ver=1, plan_id=1001)
    
    # 添加步骤
    plan.add_step(unit_id=1, cmd_id=100, args=b'\x01\x02\x03')
    plan.add_step(unit_id=2, cmd_id=200, args=b'\x04\x05\x06\x07')
    plan.add_step(unit_id=3, cmd_id=300, args=b'')
    
    print("原始数据:", plan)
    
    # 序列化
    data_bytes = plan.to_bytes()
    print(f"序列化后字节长度: {len(data_bytes)}")
    print(f"序列化后字节数据: {data_bytes.hex()}")
    
    # 反序列化
    restored_plan, size = TaskPlanData.from_bytes(data_bytes)
    print("还原数据:", restored_plan)
    
    # 验证单个 Step 的编解码
    step = Step(unit_id=5, cmd_id=999, args=b'\xAA\xBB\xCC')
    step_bytes = step.to_bytes()
    restored_step, step_size = Step.from_bytes(step_bytes)
    print(f"\nStep测试: 原始={step}, 还原={restored_step}, 大小={step_size}")
