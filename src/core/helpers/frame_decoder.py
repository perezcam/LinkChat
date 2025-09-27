import struct
import zlib  # <- para CRC-32

from src.core.enums.enums import MessageType
from src.core.enums.formats import EtherHeaderFormat, HeaderFormat
from src.core.schemas.frame_schemas import FrameSchema, HeaderSchema


def decode_ethernet_frame(frame: bytes) -> FrameSchema:
   
    eth_header_len = EtherHeaderFormat.get_len()
    dst_mac_bytes, src_mac_bytes, ethertype = struct.unpack(
        EtherHeaderFormat.get_format(), frame[:eth_header_len]
    )
    dst_mac = ':'.join(f'{b:02x}' for b in dst_mac_bytes)
    src_mac = ':'.join(f'{b:02x}' for b in src_mac_bytes)

    # ---  Header del protocolo (con checksum) ---
    hdr_len_w = HeaderFormat.get_len_with_checksum()
    hdr_fmt_w = HeaderFormat.get_format_with_checksum()
    header_start = eth_header_len
    header_end = header_start + hdr_len_w

    # Desempaquetar incluyendo checksum
    msg_type_val, sequence, payload_len, checksum_rx = struct.unpack(
        hdr_fmt_w, frame[header_start:header_end]
    )

    # ---  Payload ---
    payload_start = header_end
    payload_end = payload_start + payload_len
    payload = frame[payload_start:payload_end]

    # ---  Recalcular CRC-32 sobre (header_sin_checksum + payload) ---
    hdr_fmt_wo = HeaderFormat.get_format_without_checksum()
    header_wo = struct.pack(hdr_fmt_wo, msg_type_val, sequence, payload_len)
    checksum_calc = zlib.crc32(header_wo + payload) & 0xFFFFFFFF

    if checksum_calc != checksum_rx:
    #   lanzar excepción y que el receiver la capture y descarte
        raise ValueError(
            f"CRC inválido: esperado=0x{checksum_rx:08x}, calculado=0x{checksum_calc:08x}"
        )

    # --- Construir schemas (incluye checksum en el header) ---
    header_obj = HeaderSchema(
        message_type=MessageType(msg_type_val),
        sequence=sequence,
        payload_len=payload_len,
        checksum=checksum_rx,
    )

    return FrameSchema(
        dst_mac=dst_mac,
        src_mac=src_mac,
        ethertype=ethertype,
        header=header_obj,
        payload=payload,
    )

