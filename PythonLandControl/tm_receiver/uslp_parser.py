# 定义USLP传输帧的同步标记 (ASM - Attached Sync Marker)
USLP_SYNC_MARKER = b'\x1A\xCF\xFC\x1D'

class UslpParser:
    """
    USLP (Unified Space Data Link Protocol) 帧解析器。
    这个类负责处理原始的字节流，并从中提取出完整的USLP帧。
    """

    def __init__(self):
        """
        构造函数，初始化解析器状态。
        """
        # 创建一个字节缓冲区，用于存储从串口接收到的、尚未形成完整帧的数据
        self.buffer = bytearray()

    def parse(self, data):
        """
        核心解析方法。接收新的数据块，在内部缓冲区中寻找并提取USLP帧。

        :param data: 从串口工作线程接收到的新的原始字节数据 (bytes or bytearray)。
        :return: 一个包含所有从数据中成功解析出的完整USLP帧的列表。
        """
        # 将新接收到的数据追加到内部缓冲区的末尾
        self.buffer.extend(data)

        # 创建一个列表，用于存放本次调用中找到的所有完整帧
        found_frames = []

        # 持续在缓冲区中寻找帧，直到无法再找到为止
        while True:
            # *** 新增: 错误处理 ***
            # 使用try...except块包围核心解析逻辑，防止意外错误导致整个线程崩溃
            try:
                # 在缓冲区中查找USLP同步标记的位置
                sync_marker_pos = self.buffer.find(USLP_SYNC_MARKER)

                # 如果在缓冲区中找不到同步标记，退出循环
                if sync_marker_pos == -1:
                    break

                # 如果同步标记不在缓冲区的开头，说明标记之前的数据是噪声
                if sync_marker_pos > 0:
                    print(f"丢弃了 {sync_marker_pos} 字节的无效数据: {self.buffer[:sync_marker_pos].hex(' ')}")
                    # 通过切片操作，移除同步标记之前的所有无效数据
                    del self.buffer[:sync_marker_pos]

                # 检查缓冲区数据是否足够解析出帧头（至少8字节）
                # 帧头结构：同步标记(4) + 虚拟信道与帧长(4) = 8字节
                if len(self.buffer) < 8:
                    break

                # 从帧头中提取“虚拟信道ID和帧长度”字段 (字节4到字节7)
                vcid_and_length_field = int.from_bytes(self.buffer[4:8], byteorder='big')

                # 根据USLP标准，帧长度信息在最后16位
                frame_length_field = vcid_and_length_field & 0xFFFF
                # USLP的帧长度字段值是从0开始计数的，所以实际总长度需要+1
                total_frame_length = frame_length_field + 1

                # 检查缓冲区中的数据是否足够构成一个完整的帧
                if len(self.buffer) < total_frame_length:
                    break

                # 从缓冲区中提取出一个完整的帧 (作为不可变的bytes对象)
                full_frame = bytes(self.buffer[:total_frame_length])

                # 将这个完整的帧添加到结果列表中
                found_frames.append(full_frame)

                # 从缓冲区中移除已经提取的帧
                del self.buffer[:total_frame_length]

            except Exception as e:
                # 如果在解析过程中发生任何未预料的异常
                print(f"!!! 解析器发生严重错误: {e}")
                print("!!! 为防止程序卡死，已清空解析器缓冲区。")
                # 清空缓冲区，避免因错误数据导致无限循环的错误
                self.buffer.clear()
                # 退出循环，等待新的数据
                break

        # 返回本次调用找到的所有完整帧的列表
        return found_frames
