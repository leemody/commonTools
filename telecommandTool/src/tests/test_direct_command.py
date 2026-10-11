import binascii
import unittest

from direct_command_frame_generator import build_direct_command_frame
from low_speed_telecommand_frame_generator import build_low_speed_frame
from uslp_common import FrameProfile, build_pus_tc_packet, wrap_packet
from web_server import generate


class DirectCommandTests(unittest.TestCase):
    def test_layout_and_checksums(self):
        code = bytes(range(9))
        frame = build_direct_command_frame(command_code=code)
        self.assertEqual(len(frame), 72)
        self.assertEqual((int.from_bytes(frame[:4], 'big') >> 5) & 63, 4)
        self.assertEqual(frame[4:8], bytes.fromhex('00 47 81 00'))
        self.assertEqual(frame[8:17], b'\x5a' * 6 + bytes.fromhex('E0 FF FF'))
        packet = frame[17:54]
        self.assertEqual(packet[:11], bytes.fromhex('18 23 C0 00 00 1E 20 02 01 07 F6'))
        self.assertEqual(packet[11:-2], (bytes.fromhex('2C 79 5E') + code) * 2)
        self.assertEqual(frame[54:70], b'\x5a' * 16)
        for data in (packet, frame):
            self.assertEqual(int.from_bytes(data[-2:], 'big'), binascii.crc_hqx(data[:-2], 0xFFFF))

    def test_invalid_codes_and_fields(self):
        for length in (0, 8, 10, 24):
            with self.assertRaises(ValueError):
                build_direct_command_frame(command_code=b'\0' * length)
        for key, value in (('pid', 128), ('pcat', 16), ('scid', 65536), ('vcf_count', 256)):
            with self.assertRaises(ValueError):
                build_direct_command_frame(command_code=b'\0' * 9, **{key: value})

    def test_web_dispatch(self):
        payload = dict(kind='direct', command_code='00 01 02 03 04 05 06 07 08')
        self.assertEqual(generate(payload), build_direct_command_frame(command_code=bytes(range(9))))
        for value in ('00', 'not hex', ''):
            with self.assertRaises(ValueError):
                generate(dict(payload, command_code=value))

    def test_common_wrapper_length_limit(self):
        profile = FrameProfile(4, b'\x5a' * 6, b'\x5a' * 16)
        self.assertEqual(len(wrap_packet(packet=b'\0' * 475, scid=0, vcf_count=255, profile=profile)), 510)
        with self.assertRaises(ValueError):
            wrap_packet(packet=b'\0' * 476, scid=0, vcf_count=0, profile=profile)

    def test_common_wrapper_matches_legacy(self):
        profile = FrameProfile(5, b'\x5a' * 14, b'\x5a' * 16)
        for pid, pcat in ((0, 0), (2, 3), (127, 15)):
            packet = build_pus_tc_packet(pid=pid, pcat=pcat, service_type=2, service_subtype=2, app_data=b'\x50\x01\xaa')
            actual = wrap_packet(packet=packet, scid=0xFF01, vcf_count=0, profile=profile)
            expected = build_low_speed_frame(scid=0xFF01, vcf_count=0, pid=pid, pcat=pcat, service_type=2, service_subtype=2, command_code=0x5001, parameters=b'\xaa')
            self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
