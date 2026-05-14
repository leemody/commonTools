#ifndef CCSDS_SPACE_PACKET_H
#define CCSDS_SPACE_PACKET_H

#include <stdint.h>
#include <stddef.h>

#define SP_PRIMARY_HEADER_LEN 6
#define SP_VERSION_NUMBER 0

// --- CCSDS 空间包主包头结构体 (包含全部Header字段) ---
typedef struct {
    uint8_t  version;                  // 版本号 (3位), 通常为0
    uint8_t  type;                     // 类型 (1位): 0=遥测, 1=遥控
    uint8_t  secondary_header_flag;    // 次头标志 (1位): 0=无次头, 1=有次头
    uint16_t apid;                     // 应用进程ID (11位), 范围0-2047
    uint8_t  sequence_flags;           // 序列标志 (2位): 00=继续, 01=第一段, 10=最后一段, 11=独立包
    uint16_t sequence_count;           // 包序列计数 (14位), 范围0-16383
    uint16_t packet_data_length;       // 包数据长度 (16位), 值为(用户数据长度-1)
} ccsds_sp_header_t;

// --- 高层接口 ---

ccsds_sp_header_t ccsds_sp_header_init(void);

size_t epdu_pack(uint8_t* buffer, size_t buffer_size, const ccsds_sp_header_t* header, const uint8_t* user_data, size_t user_data_len);

size_t epdu_unpack(const uint8_t* packet_data, size_t packet_total_len, ccsds_sp_header_t* header, uint8_t* user_data_buffer, size_t user_data_buffer_size);


// --- 底层接口 (现在公开) ---

/**
 * @brief [底层接口] 将结构体形式的包头打包成二进制流。
 * @param header_buffer 用于存放结果的缓冲区。
 * @param header 指向要打包的头结构体的指针。
 */
void sp_header_pack(uint8_t* header_buffer, const ccsds_sp_header_t* header);

/**
 * @brief [底层接口] 将二进制流形式的包头解包到结构体中。
 * @param header_buffer 指向6字节包头数据的指针。
 * @param header 用于接收解析结果的结构体指针。
 */
void sp_header_unpack(const uint8_t* header_buffer, ccsds_sp_header_t* header);


#endif // CCSDS_SPACE_PACKET_H
