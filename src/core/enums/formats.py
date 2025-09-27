from enum import Enum

import struct

class HeaderFormat:
    @staticmethod
    def get_format_without_checksum() -> str:
        # message_type (H), sequence (I), payload_len (I)
        return "!HII"

    @staticmethod
    def get_format_with_checksum() -> str:
        # igual que arriba + checksum (I)
        return "!HIII"

    @staticmethod
    def get_len_without_checksum() -> int:
        return struct.calcsize(HeaderFormat.get_format_without_checksum())

    @staticmethod
    def get_len_with_checksum() -> int:
        return struct.calcsize(HeaderFormat.get_format_with_checksum())



class EtherHeaderFormat(Enum):
    """
    Formato de la cabecera Ethernet: !6s6sH
    """
    DEST_MAC = '6s'  # 6 bytes: destiny MAC address
    SRC_MAC = '6s'   # 6 bytes: origin MAC address
    ETHER_TYPE = 'H' # 2 bytes: EtherType 
    
    @classmethod
    def get_format(cls):
        return f'!{cls.DEST_MAC.value}{cls.SRC_MAC.value}{cls.ETHER_TYPE.value}'

    @classmethod
    def get_len(cls):
        return 14 #Returns total amount of bytes