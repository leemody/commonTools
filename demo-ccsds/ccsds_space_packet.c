#include "ccsds_space_packet.h"
#include <string.h>

#ifdef _WIN32
    #include <winsock2.h>
#else
    #include <arpa/inet.h>
#endif

// --- 高层接口实现 ---

ccsds_sp_header_t ccsds_sp_header_init(void) {
    ccsds_sp_header_t header;
    header.version = SP_VERSION_NUMBER;
    header.type = 0;
    header.secondary_header_flag = 0;
    header.apid = 0;
    header.sequence_flags = 0x3;
    header.sequence_count = 0;
    header.packet_data_length = 0;
    return header;
}

size_t epdu_pack(uint8_t* buffer, size_t buffer_size, const ccsds_sp_header_t* header, const uint8_t* user_data, size_t user_data_len) {
    if (!buffer || !header || (!user_data && user_data_len > 0)) {
        return 0;
    }
    if (user_data_len == 0) {
        return 0;
    }

    size_t total_len = SP_PRIMARY_HEADER_LEN + user_data_len;
    if (buffer_size < total_len) {
        return 0;
    }

    ccsds_sp_header_t header_to_pack = *header;
    header_to_pack.packet_data_length = user_data_len - 1;

    sp_header_pack(buffer, &header_to_pack);

    memcpy(buffer + SP_PRIMARY_HEADER_LEN, user_data, user_data_len);

    return total_len;
}

size_t epdu_unpack(const uint8_t* packet_data, size_t packet_total_len, ccsds_sp_header_t* header, uint8_t* user_data_buffer, size_t user_data_buffer_size) {
    if (!packet_data || !header || !user_data_buffer) {
        return 0;
    }
    if (packet_total_len < SP_PRIMARY_HEADER_LEN) {
        return 0;
    }

    sp_header_unpack(packet_data, header);

    if (header->packet_data_length + SP_PRIMARY_HEADER_LEN != packet_total_len) {
        return 0;
    }
    if (user_data_buffer_size < header->packet_data_length) {
        return 0;
    }

    memcpy(user_data_buffer, packet_data + SP_PRIMARY_HEADER_LEN, header->packet_data_length);

    return header->packet_data_length;
}

// --- 底层接口实现 (移除了static) ---

void sp_header_pack(uint8_t* header_buffer, const ccsds_sp_header_t* header) {
    uint16_t word1 = 0;
    word1 |= (header->version & 0x07) << 13;
    word1 |= (header->type & 0x01) << 12;
    word1 |= (header->secondary_header_flag & 0x01) << 11;
    word1 |= (header->apid & 0x07FF);

    word1 = htons(word1);
    memcpy(header_buffer, &word1, 2);

    uint16_t word2 = 0;
    word2 |= (header->sequence_flags & 0x03) << 14;
    word2 |= (header->sequence_count & 0x3FFF);

    word2 = htons(word2);
    memcpy(header_buffer + 2, &word2, 2);

    uint16_t word3 = htons(header->packet_data_length);
    memcpy(header_buffer + 4, &word3, 2);
}

void sp_header_unpack(const uint8_t* header_buffer, ccsds_sp_header_t* header) {
    uint16_t word1, word2, word3;
    memcpy(&word1, header_buffer, 2);
    memcpy(&word2, header_buffer + 2, 2);
    memcpy(&word3, header_buffer + 4, 2);

    word1 = ntohs(word1);
    word2 = ntohs(word2);
    word3 = ntohs(word3);

    header->version = (word1 >> 13) & 0x07;
    header->type = (word1 >> 12) & 0x01;
    header->secondary_header_flag = (word1 >> 11) & 0x01;
    header->apid = word1 & 0x07FF;

    header->sequence_flags = (word2 >> 14) & 0x03;
    header->sequence_count = word2 & 0x3FFF;

    header->packet_data_length = word3 + 1;
}
