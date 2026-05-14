#include "Frame.hpp"
#include <iostream>
#include <iomanip>

// 平台特定的网络头文件
#ifdef _WIN32
    #include <winsock2.h>
    #include <ws2tcpip.h>
    #pragma comment(lib, "ws2_32.lib")
#else
    #include <sys/socket.h>
    #include <netinet/in.h>
    #include <arpa/inet.h>
    #include <unistd.h>
    using SOCKET = int;
    const int INVALID_SOCKET = -1;
    const int SOCKET_ERROR = -1;
    #define closesocket close
#endif

// 网络层常量
constexpr int PORT = 8080;
constexpr int BUFFER_SIZE = 4096;

// 函数声明
void initializeWinsock();
void cleanupWinsock();
void handleReceivedData(const unsigned char* data, int size, const sockaddr_in& client_addr);
void printHex(const unsigned char* data, int size);

int main() {
    initializeWinsock();

    SOCKET server_socket = socket(AF_INET, SOCK_DGRAM, 0);
    if (server_socket == INVALID_SOCKET) {
        std::cerr << "错误: 套接字创建失败\n";
        cleanupWinsock();
        return 1;
    }

    sockaddr_in server_addr;
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(PORT);

    if (bind(server_socket, (struct sockaddr*)&server_addr, sizeof(server_addr)) == SOCKET_ERROR) {
        std::cerr << "错误: 绑定失败\n";
        closesocket(server_socket);
        cleanupWinsock();
        return 1;
    }

    std::cout << "✅ UDP服务器已包含Payload反序列化功能，正在监听端口 " << PORT << "...\n";

    unsigned char buffer[BUFFER_SIZE];
    sockaddr_in client_addr;
    int client_addr_len = sizeof(client_addr);

    while (true) {
        int bytes_received = recvfrom(server_socket, reinterpret_cast<char*>(buffer), BUFFER_SIZE, 0, (struct sockaddr*)&client_addr, &client_addr_len);

        if (bytes_received != SOCKET_ERROR) {
            handleReceivedData(buffer, bytes_received, client_addr);
        } else {
            std::cerr << "错误: recvfrom 失败\n";
        }
    }

    closesocket(server_socket);
    cleanupWinsock();
    return 0;
}

void handleReceivedData(const unsigned char* data, int size, const sockaddr_in& client_addr) {
    char client_ip[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &client_addr.sin_addr, client_ip, INET_ADDRSTRLEN);

    std::cout << "\n========================================\n";
    std::cout << "接收到来自 " << client_ip << ":" << ntohs(client_addr.sin_port)
              << " 的数据包，总大小: " << size << "字节\n";

    // 1. 解帧和校验
    FrameParser::DecodedFrame decoded = FrameParser::parse(data, size);

    std::cout << "  - 数据体 (Payload) 大小: " << decoded.payload.size << " 字节\n";
    std::cout << "  - 接收到的CRC-16: 0x" << std::hex << std::setw(4) << std::setfill('0') << decoded.received_crc << std::dec << "\n";
    std::cout << "  - 计算得到的CRC-16: 0x" << std::hex << std::setw(4) << std::setfill('0') << decoded.calculated_crc << std::dec << "\n";

    if (decoded.is_valid) {
        std::cout << "  - 校验结果: ✅ CRC校验通过，数据完整。\n";

        // 2. --- 新增：反序列化Payload ---
        PayloadData payload_data;
        if (FrameParser::deserialize(decoded.payload, payload_data)) {
            std::cout << "  - 反序列化成功:\n";
            std::cout << "    - Command ID: " << payload_data.command_id << "\n";
            std::cout << "    - Parameter:  " << payload_data.parameter << "\n";
        } else {
            std::cout << "  - 反序列化失败: 数据体大小 (" << decoded.payload.size
                      << "字节) 与预期结构体大小 (" << sizeof(PayloadData) << "字节) 不匹配。\n";
        }

    } else {
        std::cout << "  - 校验结果: ❌ CRC校验失败！\n";
    }
    std::cout << "========================================\n";
}

void printHex(const unsigned char* data, int size) {
    std::cout << "    ";
    for (int i = 0; i < size; ++i) {
        std::cout << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(data[i]) << " ";
        if ((i + 1) % 16 == 0 && (i + 1) < size) {
            std::cout << "\n    ";
        }
    }
    std::cout << std::dec;
}

void initializeWinsock() {
#ifdef _WIN32
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        std::cerr << "错误: WSAStartup 失败\n";
        exit(1);
    }
#endif
}

void cleanupWinsock() {
#ifdef _WIN32
    WSACleanup();
#endif
}
