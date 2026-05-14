#ifndef CCSDS_TRANSFER_FRAME_H
#define CCSDS_TRANSFER_FRAME_H

#include <stdint.h>
#include <stddef.h>

// --- 常量定义 (TM帧) ---
#define CADU_SYNC_MARKER_LEN 4
#define CADU_SYNC_MARKER 0x1ACFFC1D

#define TM_FRAME_LEN 256 // 简化帧长，便于演示
#define TM_PRIMARY_HEADER_LEN 6
#define TM_FECF_LEN 2 // 帧错误校验字段 (CRC-16)

#define TM_FRAME_DATA_ZONE_LEN (TM_FRAME_LEN - TM_PRIMARY_HEADER_LEN - TM_FECF_LEN)

/**
 * @brief 传输帧主包头结构体 (完整定义)
 */
typedef struct {
    uint8_t  version;                      // 2 bits, 版本号, 通常为 0
    uint16_t spacecraft_id;                // 10 bits, 航天器ID
    uint8_t  vc_id;                        // 3 bits, 虚拟信道ID
    uint8_t  ocf_flag;                     // 1 bit,  操作控制字段标志
    uint8_t  master_channel_frame_count;   // 8 bits, 主信道帧计数
    uint8_t  vc_frame_count;               // 8 bits, 虚拟信道帧计数
    uint8_t  sec_header_flag;              // 1 bit,  是否存在帧次包头
    uint8_t  sync_flag;                    // 1 bit,  同步标志
    uint8_t  packet_order_flag;            // 1 bit,  包顺序标志
    uint8_t  segment_len_id;               // 2 bits, 段长度标识符
    uint16_t first_header_pointer;         // 11 bits, 首包指针
} ccsds_tf_header_t;

/**
 * @brief [新增] 获取一个包含标准默认值的传输帧头。
 * @return 一个预先填充好的 ccsds_tf_header_t 结构体。
 */
ccsds_tf_header_t ccsds_tf_header_init(void);

/**
 * @brief [高层接口] 创建一个CADU (传输帧 + 同步码)。
 * @param cadu_buffer       用于存放结果的缓冲区 (大小必须 >= 4 + TM_FRAME_LEN)。
 * @param header            指向包含所有帧头信息的结构体的指针。
 * @param epdu_data         要封装的EPDU (空间包) 数据。
 * @param epdu_len          EPDU的长度。
 * @return 成功则返回CADU的总长度，失败返回0。
 */
size_t cadu_frame(uint8_t* cadu_buffer, const ccsds_tf_header_t* header, const uint8_t* epdu_data, size_t epdu_len);

/**
 * @brief [高层接口] 从一个CADU中解析出EPDU (空间包)。
 * @param cadu_data         指向CADU数据的指针。
 * @param cadu_len          CADU的总长度。
 * @param header            用于接收解析出的帧头信息的结构体指针。
 * @param epdu_buffer       用于存放提取出的EPDU的缓冲区。
 * @param epdu_buffer_size  缓冲区的最大容量。
 * @return 提取出的EPDU的实际长度。如果帧无效或缓冲区太小，则返回0。
 */
size_t cadu_deframe(const uint8_t* cadu_data, size_t cadu_len, ccsds_tf_header_t* header, uint8_t* epdu_buffer, size_t epdu_buffer_size);

#endif // CCSDS_TRANSFER_FRAME_H
