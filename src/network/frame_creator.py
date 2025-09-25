import struct
from enums.enums import MessageType
from enums.formats import EtherHeaderFormat, HeaderFormat



def _create_header(message_type: MessageType, sequence: int, payload_len: int, ether_type: int):

    header_format = HeaderFormat.get_format()
    return struct.pack(header_format, message_type.value, sequence, payload_len, ether_type)


def create_ethernet_frame(src_mac, dst_mac, payload, message_type: MessageType, sequence: int, ether_type: int):
    header = _create_header(
        message_type,
        sequence,
        len(payload),
        ether_type
    )

    ether_header_format = EtherHeaderFormat.get_format()
    ether_header = struct.pack(
        ether_header_format, 
        bytes.fromhex(dst_mac.replace(":", "")), 
        bytes.fromhex(src_mac.replace(":", "")),
        ether_type
    )

    return ether_header + header + payload.encode('utf-8')
    
    