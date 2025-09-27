import struct
import zlib 

from src.core.enums.formats import EtherHeaderFormat, HeaderFormat
from src.core.schemas.frame_schemas import FrameSchema, HeaderSchema


def _pack_header_without_checksum(header: HeaderSchema) -> bytes:
    fmt_wo = HeaderFormat.get_format_without_checksum()
    return struct.pack(fmt_wo, header.message_type.value, header.sequence, header.payload_len)


def _pack_header_with_checksum(header: HeaderSchema, checksum: int) -> bytes:
    fmt_w = HeaderFormat.get_format_with_checksum()
    return struct.pack(fmt_w, header.message_type.value, header.sequence, header.payload_len, checksum)


def create_ethernet_frame(frame_data: FrameSchema) -> bytes:
    
    header_wo = _pack_header_without_checksum(frame_data.header)

    checksum = zlib.crc32(header_wo + frame_data.payload) & 0xFFFFFFFF

    header_w = _pack_header_with_checksum(frame_data.header, checksum)

    ether_header_format = EtherHeaderFormat.get_format()
    ether_header = struct.pack(
        ether_header_format,
        bytes.fromhex(frame_data.dst_mac.replace(":", "")),
        bytes.fromhex(frame_data.src_mac.replace(":", "")),
        frame_data.ethertype,
    )

    return ether_header + header_w + frame_data.payload
