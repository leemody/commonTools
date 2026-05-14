#ifndef FRAME_HPP
#define FRAME_HPP

#include "checksum.hpp"
#include "Payload.hpp" // <-- 引入Payload结构体定义
#include <cstdint>
#include <cstddef>
#include <cstring> // for std::memcpy

namespace FrameParser {

    // ==================== 1. 公共常量和数据结构 ====================

    constexpr size_t HEADER_SIZE = 5;
    constexpr size_t CRC_SIZE = 2;
    constexpr size_t MIN_FRAME_SIZE = HEADER_SIZE + CRC_SIZE;

    struct data_view {
        const unsigned char* ptr = nullptr;
        size_t size = 0;
    };

    struct DecodedFrame {
        data_view header;
        data_view payload;
        uint16_t received_crc = 0;
        uint16_t calculated_crc = 0;
        bool is_valid = false;
    };

    // ==================== 2. 公共接口函数 ====================

    /**
     * @brief [核心接口] 解析一个原始数据缓冲区，并返回解帧结果
     */
    inline DecodedFrame parse(const unsigned char* data, size_t size) {
        DecodedFrame result;
        if (size < MIN_FRAME_SIZE) {
            return result;
        }

        result.header = {data, HEADER_SIZE};
        const size_t payload_size = size - HEADER_SIZE - CRC_SIZE;
        result.payload = {data + HEADER_SIZE, payload_size};

        const unsigned char* crc_bytes = data + HEADER_SIZE + payload_size;
        result.received_crc = (uint16_t)(crc_bytes[0] << 8) | crc_bytes[1];

        const size_t length_to_check = HEADER_SIZE + payload_size;
        result.calculated_crc = Checksum::calculateCrc16(data, length_to_check);

        result.is_valid = (result.calculated_crc == result.received_crc);

        return result;
    }

    /**
     * @brief [新增接口] 将解析出的数据体(payload)反序列化到PayloadData结构体
     * @param payload_view 从DecodedFrame中获取的payload数据视图
     * @param out_data 用于接收反序列化数据的PayloadData结构体引用
     * @return 如果payload的大小与PayloadData结构体的大小匹配，则返回true，否则返回false
     */
    inline bool deserialize(const data_view& payload_view, PayloadData& out_data) {
        if (payload_view.size != sizeof(PayloadData)) {
            // 数据体的大小与目标结构体的大小不匹配，无法安全地反序列化
            return false;
        }
        // 使用memcpy从视图的指针安全地拷贝内存到结构体
        std::memcpy(&out_data, payload_view.ptr, sizeof(PayloadData));
        return true;
    }

} // namespace FrameParser

#endif // FRAME_HPP
