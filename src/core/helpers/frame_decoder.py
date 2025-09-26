import struct


from src.core.enums.enums import MessageType
from src.core.enums.formats import EtherHeaderFormat, HeaderFormat
from src.core.schemas.frame_schemas import FrameSchema, HeaderSchema



def decode_ethernet_frame(frame: bytes) -> FrameSchema:
    eth_header_len = EtherHeaderFormat.get_len()
    custom_header_len = HeaderFormat.get_len()

    dst_mac_bytes, src_mac_bytes, ethertype = struct.unpack(
        EtherHeaderFormat.get_format(), frame[:eth_header_len]
    )   
    dst_mac = ':'.join(f'{b:02x}' for b in dst_mac_bytes)
    src_mac = ':'.join(f'{b:02x}' for b in src_mac_bytes)


    header_start = eth_header_len
    header_end = header_start + custom_header_len
    
    msg_type_val, sequence, payload_len = struct.unpack(
        HeaderFormat.get_format(), frame[header_start:header_end]
    )
    
    header_obj = HeaderSchema(
        message_type=MessageType(msg_type_val),
        sequence=sequence,
        payload_len=payload_len
    )

    payload_start = header_end
    payload = frame[payload_start : payload_start + payload_len]

    return FrameSchema(
        dst_mac=dst_mac,
        src_mac=src_mac,
        ethertype=ethertype,
        header=header_obj,
        payload=payload
    )


#TODO: Descartar aqui los que no sean de mi EtherTYpe??? o hacerlo en el pool de hilos?
