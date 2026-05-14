from udp_client import UDPClient
from data_model import TargetData
from epdu_header import EpduHeader
from epdu_packet import EpduPacket
from telecommand_frame import TelecommandFrame
import os

def main():
    # 配置文件路径
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    # 1. 从配置文件读取并映射为数据区对象
    try:
        payload_data = TargetData.from_json(config_path)
        print("成功从配置文件加载数据区。")
    except Exception as e:
        print(f"读取配置文件失败: {e}")
        return

    # 2. 构造包头
    # 假设：版本号 0, pt 为 1, APID 为 8, sf 为 3 (可根据实际需求修改)
    header = EpduHeader(ver=0, pt=1, apid=8, sf=3)

    # 3. 组装为完整 EPDU 包
    packet = EpduPacket(header=header, payload=payload_data)

    # 4. 执行 EPDU 打包(此时会自动计算数据区长度填充进包头，包括指令头)
    epdu_bytes = packet.pack()
    
    # ==========================
    # 新增: 封装到遥控帧
    # ==========================
    # 假设帧头为 5 个字节: 0xEB 0x90 0xEB 0x90 0x01
    frame_header = b'\xEB\x90\xEB\x90\x01'
    frame = TelecommandFrame(data=epdu_bytes, header_bytes=frame_header)
    frame_bytes = frame.pack()
    
    # ==========================
    # 打印测试
    # ==========================
    hex_output = ' '.join(f'{b:02X}' for b in frame_bytes)
    print(f"\n准备发送的完整遥控帧 (头(5) + EPDU包({len(epdu_bytes)}) + CRC(2)) (16进制, 总长 {len(frame_bytes)} 字节):")
    print(hex_output)

    print("\nEPDU 完整包 JSON 映射:")
    print(packet.to_json_string())

    print("\n--- 逆运算测试 ---")
    try:
        # 先解析出遥控帧
        parsed_frame = TelecommandFrame.unpack(frame_bytes)
        print("遥控帧逆运算(CRC校验)成功！提取出有效 EPDU 数据区。")
        
        # 再解析 EPDU 数据
        parsed_packet = EpduPacket.unpack(parsed_frame.data)
        print("EPDU 数据解析成功！得到的内容:")
        print(parsed_packet.to_json_string())
    except Exception as e:
        print(f"逆运算失败: {e}")
    print("-" * 50 + "\n")

    # ==========================
    # 5. 网络发送
    # ==========================
    client = UDPClient("127.0.0.1", 8080)
    # 最终发送的是完整的遥控帧数据
    client.send_data(frame_bytes)
    client.close()

if __name__ == "__main__":
    main()
