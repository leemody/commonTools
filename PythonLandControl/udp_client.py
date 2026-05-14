import socket

class UDPClient:
    def __init__(self, target_ip, target_port):
        """
        初始化 UDP 客户端
        :param target_ip: 目标服务器的 IP 地址
        :param target_port: 目标服务器的端口号
        """
        self.target_ip = target_ip
        self.target_port = target_port
        # 创建 UDP Socket (AF_INET 表示 IPv4, SOCK_DGRAM 表示 UDP)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
    def send_data(self, data):
        """
        发送数据
        :param data: 要发送的数据，可以是字符串或字节流
        """
        try:
            # 如果是字符串，则先编码为 utf-8 字节流
            if isinstance(data, str):
                data = data.encode('utf-8')
                
            # 发送数据到指定的目标 IP 和端口
            self.sock.sendto(data, (self.target_ip, self.target_port))
            print(f"数据发送成功: {self.target_ip}:{self.target_port}")
        except Exception as e:
            print(f"发送数据时出错: {e}")
            
    def close(self):
        """
        关闭 Socket 连接
        """
        self.sock.close()
