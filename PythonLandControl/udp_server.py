import socket
from epdu_packet import EpduPacket
from telecommand_frame import TelecommandFrame

class UDPServer:
    def __init__(self, host, port):
        """
        初始化 UDP 服务端 (监听端)
        :param host: 监听的 IP，如果是 "0.0.0.0" 则监听所有网卡
        :param port: 监听的端口号
        """
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 绑定 IP 和端口
        self.sock.bind((self.host, self.port))
        
    def start_listening(self):
        """
        启动持续监听，接收并解析数据
        """
        print(f"\n[服务端启动] 正在监听 UDP 端口 {self.host}:{self.port} ...")
        print("按 Ctrl+C 可以停止监听。\n")
        
        try:
            while True:
                # 接收数据 (最大接收 1024 字节)
                data, addr = self.sock.recvfrom(1024)
                print(f"--- 收到来自 {addr} 的数据 ---")
                
                # 1. 打印原始 16 进制流
                hex_str = ' '.join(f'{b:02X}' for b in data)
                print(f"数据内容 (16进制, 长度 {len(data)}): {hex_str}")
                
                # 2. 尝试按照完整遥控帧格式进行解包并打印 JSON
                try:
                    # 先解包遥控帧，验证 CRC
                    parsed_frame = TelecommandFrame.unpack(data)
                    print("遥控帧解析和 CRC 校验成功！")
                    
                    # 提取数据区，再按照 EPDU 格式解包
                    parsed_packet = EpduPacket.unpack(parsed_frame.data)
                    print("EPDU 数据包映射为 JSON 对象:")
                    print(parsed_packet.to_json_string())
                        
                except Exception as parse_err:
                    print(f"解析数据失败: {parse_err}")
                
                print("-" * 50)
                
        except KeyboardInterrupt:
            print("\n监听已手动停止。")
        except Exception as e:
            print(f"监听时发生错误: {e}")
        finally:
            self.close()

    def close(self):
        """
        关闭 Socket
        """
        self.sock.close()
        print("UDP 服务端 Socket 已关闭。")

if __name__ == "__main__":
    # 示例运行：监听本地 8080 端口
    server = UDPServer("127.0.0.1", 8080)
    server.start_listening()
