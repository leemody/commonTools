#ifndef PAYLOAD_HPP
#define PAYLOAD_HPP

#include <cstdint>

/**
 * @brief 使用 #pragma pack 来确保结构体成员之间没有额外的填充字节。
 * 这对于从网络缓冲区直接映射内存至关重要，可以保证内存布局与数据流中的字节完全一致。
 */
#pragma pack(push, 1)

/**
 * @brief 定义了数据体（Payload）的确切二进制结构。
 */
struct PayloadData {
    uint32_t command_id;  // 4字节的命令ID
    int32_t  parameter;   // 4字节的参数
};

#pragma pack(pop)

#endif // PAYLOAD_HPP
