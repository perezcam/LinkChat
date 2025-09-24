import struct

from enums.formats import EtherHeaderFormat, HeaderFormat
from src.network.schemas.frame_schemas import FrameSchema, HeaderSchema



def _create_header(header: HeaderSchema) -> bytes:
    header_format = HeaderFormat.get_format()
    return struct.pack(header_format, header.message_type.value, header.sequence, header.payload_len)


def create_ethernet_frame(frame_data : FrameSchema):

    header = _create_header(frame_data.header)

    ether_header_format = EtherHeaderFormat.get_format()
    ether_header = struct.pack(
        ether_header_format, 
        bytes.fromhex(frame_data.dst_mac.replace(":", "")), 
        bytes.fromhex(frame_data.src_mac.replace(":", "")),
        frame_data.ethertype,
    )

    return ether_header + header + frame_data.payload
    
    