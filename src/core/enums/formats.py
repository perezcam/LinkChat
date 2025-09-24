from enum import Enum

class HeaderFormat(Enum):
    MESSAGE_TYPE = 'B'  # 1 byte: message type
    SEQUENCE = 'H'      # 2 bytes: sequence number
    PAYLOAD_LEN = 'I'   # 4 bytes: payload size
    
    @classmethod
    def get_format(cls):
        return f'!{cls.MESSAGE_TYPE.value}{cls.SEQUENCE.value}{cls.PAYLOAD_LEN.value}'
    
    @classmethod
    def get_len(cls):
        return 7 #Returns total amount of bytes


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