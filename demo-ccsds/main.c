#include "ccsds_space_packet.h"
#include "ccsds_transfer_frame.h"
#include <stdio.h>
#include <string.h>

void print_hex(const char* title, const uint8_t* data, size_t len) {
    printf("%s (%zu bytes):\n", title, len);
    for (size_t i = 0; i < len; ++i) {
        printf("%02X ", data[i]);
        if ((i + 1) % 16 == 0 && (i + 1) < len) {
            printf("\n");
        }
    }
    printf("\n\n");
}

int main() {
    printf("--- CCSDS Packing and Framing Demo (Refactored) ---\n\n");

    // ==================== 1. 准备用户数据 ====================
    const char* user_message = "Hello from refactored C code!";
    size_t user_data_len = strlen(user_message) + 1;

    printf("Original User Data: \"%s\"\n\n", user_message);

    // ==================== 2. [组包] 创建EPDU (空间包) ====================
    // 2.1 获取默认包头并按需修改
    ccsds_sp_header_t sp_header = ccsds_sp_header_init();
    sp_header.type = 1; // 1 = Telecommand
    sp_header.apid = 102;
    sp_header.sequence_count = 1;

    // 2.2 调用组包接口
    uint8_t epdu_buffer[256];
    size_t epdu_len = epdu_pack(epdu_buffer, sizeof(epdu_buffer), &sp_header, (const uint8_t*)user_message, user_data_len);
    if (epdu_len == 0) {
        printf("EPDU packing failed!\n");
        return 1;
    }
    print_hex("Packed EPDU (Space Packet)", epdu_buffer, epdu_len);

    // ==================== 3. [组帧] 创建CADU (传输帧) ====================
    // 3.1 获取默认帧头并按需修改
    ccsds_tf_header_t tf_header = ccsds_tf_header_init();
    tf_header.spacecraft_id = 512;
    tf_header.vc_id = 3;
    tf_header.master_channel_frame_count = 10;
    tf_header.vc_frame_count = 20;

    // 3.2 调用组帧接口
    uint8_t cadu_buffer[CADU_SYNC_MARKER_LEN + TM_FRAME_LEN];
    size_t cadu_len = cadu_frame(cadu_buffer, &tf_header, epdu_buffer, epdu_len);
    if (cadu_len == 0) {
        printf("CADU framing failed!\n");
        return 1;
    }
    print_hex("Framed CADU (Sync Marker + Transfer Frame)", cadu_buffer, cadu_len);

    printf("\n--- CCSDS De-framing and Unpacking Demo ---\n\n");

    // ==================== 4. [解帧] 从CADU中解析出EPDU ====================
    ccsds_tf_header_t received_tf_header;
    uint8_t received_epdu_buffer[256];
    size_t received_epdu_len = cadu_deframe(cadu_buffer, cadu_len, &received_tf_header, received_epdu_buffer, sizeof(received_epdu_buffer));
    if (received_epdu_len == 0) {
        printf("CADU de-framing failed! (Sync, CRC, or length error)\n");
        return 1;
    }
    printf("De-framed successfully! VC_ID: %u, VC Frame Count: %u\n", received_tf_header.vc_id, received_tf_header.vc_frame_count);
    print_hex("Extracted EPDU", received_epdu_buffer, received_epdu_len);

    // ==================== 5. [解包] 从EPDU中解析出用户数据 ====================
    ccsds_sp_header_t received_sp_header;
    uint8_t final_user_data[128];
    size_t final_user_data_len = epdu_unpack(received_epdu_buffer, received_epdu_len, &received_sp_header, final_user_data, sizeof(final_user_data));
    if (final_user_data_len == 0) {
        printf("EPDU unpacking failed!\n");
        return 1;
    }

    printf("Unpacked successfully! Type: %u, APID: %u, Seq Count: %u\n", received_sp_header.type, received_sp_header.apid, received_sp_header.sequence_count);
    printf("Final Recovered User Data: \"%s\"\n", final_user_data);

    // ==================== 6. 验证 ====================
    if (strcmp(user_message, (char*)final_user_data) == 0) {
        printf("\n✅ Verification successful! Recovered data matches original data.\n");
    } else {
        printf("\n❌ Verification failed! Data mismatch.\n");
    }

    return 0;
}
