import binascii
import unittest

from high_speed_frame_generator import build_high_speed_frame, high_speed_profile
from high_speed_idle_frame_generator import build_high_speed_idle_frame, pn_sequence
from uslp_common import wrap_packet
from web_server import generate


class HighSpeedTests(unittest.TestCase):
    def check_frame(self, frame, vcid, map_id):
        self.assertEqual(len(frame), 1020)
        self.assertEqual(frame[4:7], bytes.fromhex('03 FB 81'))
        word=int.from_bytes(frame[:4], 'big')
        self.assertEqual((word>>5)&63,vcid)
        self.assertEqual((word>>1)&15,map_id)
        self.assertEqual(word&1,0)
        self.assertEqual(frame[8:22], b'\x5A'*14)
        self.assertEqual(frame[1002:1018], b'\x5A'*16)
        self.assertEqual(int.from_bytes(frame[-2:],'big'),binascii.crc_hqx(frame[:-2],0xFFFF))

    def test_data_variants(self):
        for limit in (964,):
            for size in (0,1,limit):
                for map_id in (1,14):
                    for flags in range(4):
                        data=bytes(i%256 for i in range(size))
                        frame=build_high_speed_frame(app_data=data,map_id=map_id,sequence_flags=flags,sequence_count=16383,vcf_count=255)
                        self.check_frame(frame,10,map_id)
                        packet=frame[25:25+13+size]
                        self.assertEqual(frame[22],0x20)
                        self.assertEqual(int.from_bytes(frame[23:25],'big'),len(packet)-1)
                        self.assertEqual(packet[9:11],bytes.fromhex('07 F6'))
                        self.assertEqual(packet[7:9],b'\x02\x02')
                        self.assertEqual(int.from_bytes(packet[2:4],'big'),(flags<<14)|16383)
                        self.assertEqual(int.from_bytes(packet[4:6],'big')+7,len(packet))
                        self.assertEqual(packet[11:-2],data)
                        self.assertEqual(int.from_bytes(packet[-2:],'big'),binascii.crc_hqx(packet[:-2],0xFFFF))
                        self.assertEqual(frame[25+len(packet):1002],b'\xAA'*(977-len(packet)))

    def test_pn_reference_and_recurrence(self):
        pn=pn_sequence()
        self.assertEqual(pn[:20],bytes.fromhex('FF FF FF FF 6D B6 D8 61 45 1F 11 F1 97 16 72 3C BE 7E 00 B1'))
        bits=[1]*32
        for i in range(977*8-32):
            bits.append(bits[i]^bits[i+10]^bits[i+30]^bits[i+31])
        reference=bytes(sum(bits[i+j]<<(7-j) for j in range(8)) for i in range(0,len(bits),8))
        self.assertEqual(pn,reference)
        for count in (0,255):
            frame=build_high_speed_idle_frame(vcf_count=count)
            self.check_frame(frame,63,0)
            self.assertEqual(frame[22:25],bytes.fromhex('20 FF FE'))
            self.assertEqual(frame[25:1002],reference)
            self.assertEqual(frame[7],count)

    def test_boundaries(self):
        for args in [dict(app_data=b'\0'*965),dict(app_data='invalid'),
                     dict(map_id=0),dict(sequence_flags=4),dict(sequence_count=16384),
                     dict(vcf_count=256),dict(pid=128),dict(pcat=16),dict(scid=-1)]:
            with self.assertRaises(ValueError): build_high_speed_frame(**args)
        with self.assertRaises(ValueError): build_high_speed_idle_frame(vcf_count=256)
        frame=wrap_packet(packet=b'\0'*977,scid=0xFF01,vcf_count=0,profile=high_speed_profile())
        self.check_frame(frame,10,14)
        with self.assertRaises(ValueError): wrap_packet(packet=b'\0'*978,scid=0,vcf_count=0,profile=high_speed_profile())

    def test_vcid_choices(self):
        default = build_high_speed_frame(app_data=bytes((1, 2)))
        for vcid in (10, 5, 4, 63):
            with self.subTest(vcid=vcid):
                frame = build_high_speed_frame(app_data=bytes((1, 2)), vcid=vcid)
                self.check_frame(frame, vcid, 14)
                self.assertEqual(frame[4:-2], default[4:-2])
                self.assertEqual(generate({'kind': 'high', 'vcid': str(vcid),
                                           'app_data': '01 02'}), frame)

    def test_vcid_defaults(self):
        expected = build_high_speed_frame()
        self.check_frame(expected, 10, 14)
        for request in ({'kind': 'high'}, {'kind': 'high', 'vcid': ''},
                        {'kind': 'high', 'vcid': None}):
            self.assertEqual(generate(request), expected)

    def test_invalid_vcid(self):
        for vcid in (0, 6, -1, 64, True, 10.0, 'bad'):
            with self.subTest(vcid=vcid):
                with self.assertRaises(ValueError):
                    build_high_speed_frame(vcid=vcid)
                with self.assertRaises(ValueError):
                    generate({'kind': 'high', 'vcid': vcid})

    def test_dispatch(self):
        self.assertEqual(generate({'kind':'high','app_data':'01 02'}),build_high_speed_frame(app_data=b'\x01\x02'))
        self.assertEqual(generate({'kind':'high_idle'}),build_high_speed_idle_frame())
        with self.assertRaises(ValueError): generate({'kind':'high','app_data':'xyz'})


if __name__=='__main__': unittest.main()
