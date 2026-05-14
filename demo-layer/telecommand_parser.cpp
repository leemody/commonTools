#include <iostream>
#include <cstdint>
#include <cstring>
#include <iomanip>

// ==========================================
// 1. EPDU 源包头结构 (6 字节)
// ==========================================
#pragma pack(push, 1)
struct TypeEpduHeader {
    // 假设在小端(Little-Endian)机器上编译，位域从低位到高位排列
    uint16_t ver : 3;
    uint16_t pt : 1;
    uint16_t shf : 1;
    uint16_t apid : 11;

    uint16_t sf : 2;
    uint16_t psc : 14;

    uint16_t len : 16;
};
#pragma pack(pop)


// ==========================================
// 2. 核心数据 (Payload) (73 字节)
// ==========================================
#pragma pack(push, 1)
struct PayloadData {
    double target_coordinates[3]; // 3 * 8 = 24 bytes
    char coordinate_system[16];   // 16 bytes
    double duration;              // 8 bytes
    double position_accuracy;     // 8 bytes
    double velocity_accuracy;     // 8 bytes
    double stay_duration;         // 8 bytes
    bool allow_continue;          // 1 byte
};
#pragma pack(pop)


// ==========================================
// 3. 遥控数据与解析系统类 (完全去除动态内存)
// ==========================================
class TelecommandSystem {
public:
    // 计算 CRC-16 (CCITT/CCSDS 标准)
    static uint16_t calculate_crc16(const uint8_t* data, size_t length) {
        uint16_t crc = 0xFFFF;
        for (size_t i = 0; i < length; ++i) {
            crc ^= (static_cast<uint16_t>(data[i]) << 8);
            for (int j = 0; j < 8; ++j) {
                if (crc & 0x8000) {
                    crc = (crc << 1) ^ 0x1021;
                } else {
                    crc = (crc << 1);
                }
            }
        }
        return crc;
    }

    // --- 组包流程 ---

    // 步骤 A: 将数据区(指令头 + 核心数据)打包为字节流
    // 返回: true 表示成功，false 表示 out_buffer 空间不足
    static bool pack_target_data(
        uint8_t service_type, uint8_t unit_count, uint8_t unit_type, uint8_t device_id,
        const PayloadData& payload,
        uint8_t* out_buffer, size_t max_len, size_t& out_len)
    {
        uint16_t payload_len = sizeof(PayloadData); // 73 bytes
        // 指令单元长度 (单元类型码 + 设备号 + 长度H + 长度L + 核心数据长度)
        uint16_t command_unit_len = 1 + 1 + 2 + payload_len;

        // 总计占用的长度：服务类型(1) + 单元个数(1) + 单元类型(1) + 设备号(1) + 长度(2) + Payload
        out_len = 6 + payload_len;

        if (out_len > max_len) {
            return false;
        }

        // 写入指令头 (大端模式写入长度)
        out_buffer[0] = service_type;
        out_buffer[1] = unit_count;
        out_buffer[2] = unit_type;
        out_buffer[3] = device_id;
        out_buffer[4] = (command_unit_len >> 8) & 0xFF; // 长度H
        out_buffer[5] = command_unit_len & 0xFF;        // 长度L

        // 写入核心数据 (小端模式直接内存拷贝)
        memcpy(out_buffer + 6, &payload, payload_len);

        return true;
    }

    // 步骤 B: 组装完整的 EPDU 包 (源包头 + 数据区)
    static bool pack_epdu_packet(
        TypeEpduHeader header,
        const uint8_t* target_data, size_t target_data_len,
        uint8_t* out_buffer, size_t max_len, size_t& out_len)
    {
        out_len = sizeof(TypeEpduHeader) + target_data_len;
        if (out_len > max_len) {
            return false;
        }

        // 自动填入长度
        header.len = static_cast<uint16_t>(target_data_len);

        // 拷贝包头
        memcpy(out_buffer, &header, sizeof(TypeEpduHeader));
        // 拷贝数据区
        memcpy(out_buffer + sizeof(TypeEpduHeader), target_data, target_data_len);

        return true;
    }

    // 步骤 C: 组装成最终的数据遥控帧 (帧头 + EPDU包 + CRC校验码)
    static bool pack_telecommand_frame(
        const uint8_t* frame_header, size_t header_len,
        const uint8_t* epdu_bytes, size_t epdu_len,
        uint8_t* out_buffer, size_t max_len, size_t& out_len)
    {
        out_len = header_len + epdu_len + 2; // +2字节用于CRC
        if (out_len > max_len) {
            return false;
        }

        // 拷贝帧头
        memcpy(out_buffer, frame_header, header_len);
        // 拷贝 EPDU 包
        memcpy(out_buffer + header_len, epdu_bytes, epdu_len);

        // 计算整个帧(不含校验码)的 CRC
        uint16_t crc = calculate_crc16(out_buffer, header_len + epdu_len);

        // 大端模式追加 CRC
        out_buffer[header_len + epdu_len] = (crc >> 8) & 0xFF;
        out_buffer[header_len + epdu_len + 1] = crc & 0xFF;

        return true;
    }

    // --- 解包流程 (逆运算) ---

    // 步骤 A: 解帧与 CRC 校验
    static bool unpack_telecommand_frame(
        const uint8_t* frame_bytes, size_t frame_len, size_t header_len,
        const uint8_t*& out_epdu_data, size_t& out_epdu_len)
    {
        if (frame_len < header_len + 2) {
            std::cerr << "数据帧长度太短" << std::endl;
            return false;
        }

        // 计算预期的 CRC
        uint16_t expected_crc = calculate_crc16(frame_bytes, frame_len - 2);
        // 提取收到的 CRC
        uint16_t received_crc = (frame_bytes[frame_len - 2] << 8) | frame_bytes[frame_len - 1];

        if (expected_crc != received_crc) {
            std::cerr << "CRC 校验失败!" << std::endl;
            return false;
        }

        // 返回包含 EPDU 包的数据段起始指针和长度
        out_epdu_data = frame_bytes + header_len;
        out_epdu_len = frame_len - header_len - 2;
        return true;
    }

    // 步骤 B: 解析 EPDU 包
    static bool unpack_epdu_packet(
        const uint8_t* epdu_bytes, size_t epdu_len,
        TypeEpduHeader& out_header,
        const uint8_t*& out_target_data, size_t& out_target_data_len)
    {
        if (epdu_len < sizeof(TypeEpduHeader)) {
            std::cerr << "EPDU 包长度不足以包含包头" << std::endl;
            return false;
        }

        // 拷贝出包头
        memcpy(&out_header, epdu_bytes, sizeof(TypeEpduHeader));

        // 检查包长指示是否合法
        if (epdu_len < sizeof(TypeEpduHeader) + out_header.len) {
            std::cerr << "EPDU 包长度与包头指示不符" << std::endl;
            return false;
        }

        // 提取出 TargetData 数据区
        out_target_data = epdu_bytes + sizeof(TypeEpduHeader);
        out_target_data_len = out_header.len;
        return true;
    }

    // 步骤 C: 解析指令头与核心数据
    static bool unpack_target_data(
        const uint8_t* target_data_bytes, size_t target_data_len,
        uint8_t& out_svc, uint8_t& out_uc, uint8_t& out_ut, uint8_t& out_did, uint16_t& out_len,
        PayloadData& out_payload)
    {
        if (target_data_len < 6 + sizeof(PayloadData)) {
            std::cerr << "数据区长度不足以包含指令头和核心数据" << std::endl;
            return false;
        }

        out_svc = target_data_bytes[0];
        out_uc = target_data_bytes[1];
        out_ut = target_data_bytes[2];
        out_did = target_data_bytes[3];
        out_len = (target_data_bytes[4] << 8) | target_data_bytes[5]; // 解析大端长度

        memcpy(&out_payload, target_data_bytes + 6, sizeof(PayloadData));
        return true;
    }

    // 辅助打印函数: 16进制打印
    static void print_hex(const uint8_t* data, size_t len) {
        for (size_t i = 0; i < len; ++i) {
            std::cout << std::hex << std::setw(2) << std::setfill('0') << (int)data[i] << " ";
        }
        std::cout << std::dec << std::endl;
    }
};

// ==========================================
// 4. 测试主函数
// ==========================================
// 定义固定的最大缓存大小，完全避免动态内存分配 (new, std::vector 等)
#define MAX_BUFFER_SIZE 256

int main() {
    std::cout << "--- 1. 准备核心数据 ---" << std::endl;
    PayloadData payload;
    memset(&payload, 0, sizeof(PayloadData));
    payload.target_coordinates[0] = 120.15;
    payload.target_coordinates[1] = 30.28;
    payload.target_coordinates[2] = 35.5;
    strncpy(payload.coordinate_system, "WGS84", 16);
    payload.duration = 10.5;
    payload.position_accuracy = 0.1;
    payload.velocity_accuracy = 0.05;
    payload.stay_duration = 5.0;
    payload.allow_continue = true;

    // --- 申请静态分配的数组作为缓存 ---
    uint8_t target_data_buf[MAX_BUFFER_SIZE];
    size_t target_data_len = 0;

    uint8_t epdu_buf[MAX_BUFFER_SIZE];
    size_t epdu_len = 0;

    uint8_t frame_buf[MAX_BUFFER_SIZE];
    size_t frame_len = 0;

    // --- 正向组包组帧 ---

    // A. 组装数据区 (指令头 + 核心数据)
    if (!TelecommandSystem::pack_target_data(0x50, 0x01, 0xF7, 0x01, payload, target_data_buf, MAX_BUFFER_SIZE, target_data_len)) {
        std::cerr << "打包 TargetData 失败 (缓冲区不足)" << std::endl;
        return -1;
    }

    // B. 构造 EPDU 包头
    TypeEpduHeader epdu_header;
    memset(&epdu_header, 0, sizeof(TypeEpduHeader));
    epdu_header.ver = 0;
    epdu_header.pt = 1;
    epdu_header.apid = 8;
    epdu_header.sf = 3;

    // 组装完整 EPDU 包
    if (!TelecommandSystem::pack_epdu_packet(epdu_header, target_data_buf, target_data_len, epdu_buf, MAX_BUFFER_SIZE, epdu_len)) {
        std::cerr << "打包 EPDU 失败 (缓冲区不足)" << std::endl;
        return -1;
    }

    // C. 组装最终遥控帧
    uint8_t frame_header[5] = {0xEB, 0x90, 0xEB, 0x90, 0x01};
    if (!TelecommandSystem::pack_telecommand_frame(frame_header, 5, epdu_buf, epdu_len, frame_buf, MAX_BUFFER_SIZE, frame_len)) {
        std::cerr << "打包遥控帧失败 (缓冲区不足)" << std::endl;
        return -1;
    }

    std::cout << "\n最终生成的完整数据遥控帧 (16进制, " << frame_len << " 字节):" << std::endl;
    TelecommandSystem::print_hex(frame_buf, frame_len);


    // --- 逆向解帧解包 ---
    std::cout << "\n--- 2. 开始逆向解帧解包 ---" << std::endl;

    // A. 解帧验证 CRC
    const uint8_t* parsed_epdu_ptr = nullptr;
    size_t parsed_epdu_len = 0;
    if (!TelecommandSystem::unpack_telecommand_frame(frame_buf, frame_len, 5, parsed_epdu_ptr, parsed_epdu_len)) {
        return -1;
    }
    std::cout << "[成功] 遥控帧 CRC 校验通过!" << std::endl;

    // B. 解析 EPDU 包
    TypeEpduHeader parsed_header;
    const uint8_t* parsed_target_data_ptr = nullptr;
    size_t parsed_target_data_len = 0;
    if (!TelecommandSystem::unpack_epdu_packet(parsed_epdu_ptr, parsed_epdu_len, parsed_header, parsed_target_data_ptr, parsed_target_data_len)) {
        return -1;
    }
    std::cout << "[成功] EPDU 包解析通过! APID: " << parsed_header.apid << ", 数据区长度: " << parsed_header.len << std::endl;

    // C. 解析指令头与核心数据
    uint8_t svc, uc, ut, did;
    uint16_t cmd_len;
    PayloadData parsed_payload;
    if (!TelecommandSystem::unpack_target_data(parsed_target_data_ptr, parsed_target_data_len, svc, uc, ut, did, cmd_len, parsed_payload)) {
        return -1;
    }

    std::cout << "[成功] 指令头与核心数据解析通过!" << std::endl;
    std::cout << "  服务类型: 0x" << std::hex << (int)svc << std::dec << std::endl;
    std::cout << "  单元类型: 0x" << std::hex << (int)ut << std::dec << std::endl;
    std::cout << "  目标点 X: " << parsed_payload.target_coordinates[0] << std::endl;
    std::cout << "  坐标系: " << parsed_payload.coordinate_system << std::endl;
    std::cout << "  是否继续: " << (parsed_payload.allow_continue ? "true" : "false") << std::endl;

    return 0;
}
