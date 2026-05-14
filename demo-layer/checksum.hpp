#ifndef CHECKSUM_HPP
#define CHECKSUM_HPP

#include <cstdint>
#include <vector>

namespace Checksum {

    /**
     * @brief 计算CRC-16/CCITT-FALSE校验码
     * 这是一个在工业和通信领域广泛使用的16位CRC标准。
     * 多项式: 0x1021, 初始值: 0xFFFF, 结果无反转
     * @param data 指向要校验的数据的指针
     * @param length 数据的长度（字节）
     * @return 16位CRC校验码
     */
    inline uint16_t calculateCrc16(const unsigned char* data, size_t length) {
        uint16_t crc = 0xFFFF;
        for (size_t i = 0; i < length; ++i) {
            crc ^= (uint16_t)data[i] << 8;
            for (int j = 0; j < 8; ++j) {
                if (crc & 0x8000) {
                    crc = (crc << 1) ^ 0x1021;
                } else {
                    crc <<= 1;
                }
            }
        }
        return crc;
    }

} // namespace Checksum

#endif // CHECKSUM_HPP
