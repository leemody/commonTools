#ifndef CRC16_H
#define CRC16_H

#include <stdint.h>
#include <stddef.h>

/**
 * @brief 计算给定数据的CRC-16/CCITT-FALSE校验码
 * @param data 指向要校验的数据的指针
 * @param length 数据的长度（字节）
 * @return 16位CRC校验码
 */
uint16_t crc16_ccitt_false(const uint8_t* data, size_t length);

#endif // CRC16_H