import struct

class EpduHeader:
    """
    EPDU 源包头结构 (共 6 字节)
    对应 C 语言的带位域(Bit-field)的 struct TypeEpduHeader:
    typedef struct {
      uint16 ver:3;
      uint16 pt:1;
      uint16 shf:1;
      uint16 apid:11;
      uint16 sf:2;
      uint16 psc:14;
      uint16 len:16;
    } __attribute__ ((packed)) TypeEpduHeader;
    
    假设编译器为小端模式(Little-Endian)，位域从低位(LSB)向高位(MSB)分配。
    """
    HEADER_FORMAT = '<HHH'  # 3 个 16位无符号整数(小端)
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT) # 6 bytes

    def __init__(self, ver=0, pt=0, shf=0, apid=0, sf=0, psc=0, payload_len=0):
        self.ver = ver      # 3 bits
        self.pt = pt        # 1 bit
        self.shf = shf      # 1 bit
        self.apid = apid    # 11 bits
        self.sf = sf        # 2 bits
        self.psc = psc      # 14 bits
        self.len = payload_len # 16 bits (包长，通常指数据区的长度)

    def pack(self):
        """
        利用位运算拼接位域，打包为 6 字节的二进制流
        """
        # 第一个 uint16: ver(3) | pt(1) | shf(1) | apid(11)
        word1 = (self.ver & 0x07) | ((self.pt & 0x01) << 3) | ((self.shf & 0x01) << 4) | ((self.apid & 0x7FF) << 5)
        # 第二个 uint16: sf(2) | psc(14)
        word2 = (self.sf & 0x03) | ((self.psc & 0x3FFF) << 2)
        # 第三个 uint16: len(16)
        word3 = self.len & 0xFFFF
        
        return struct.pack(self.HEADER_FORMAT, word1, word2, word3)

    @classmethod
    def unpack(cls, header_bytes):
        """
        将 6 字节二进制流解包为对象
        """
        word1, word2, word3 = struct.unpack(cls.HEADER_FORMAT, header_bytes[:6])
        
        ver = word1 & 0x07
        pt = (word1 >> 3) & 0x01
        shf = (word1 >> 4) & 0x01
        apid = (word1 >> 5) & 0x7FF
        
        sf = word2 & 0x03
        psc = (word2 >> 2) & 0x3FFF
        
        payload_len = word3
        return cls(ver, pt, shf, apid, sf, psc, payload_len)

    def to_dict(self):
        """
        转换为字典方便 JSON 序列化
        """
        return {
            "ver": self.ver, "pt": self.pt, "shf": self.shf,
            "apid": self.apid, "sf": self.sf, "psc": self.psc,
            "len": self.len
        }
