from dataclasses import dataclass

from src.network.enums.enums import MessageType

@dataclass(frozen=True)
class HeaderSchema:
    message_type: MessageType
    sequence: int
    payload_len: int

@dataclass(frozen=True)
class FrameSchema:
    dst_mac: str
    src_mac: str
    ethertype: int 
    header: HeaderSchema
    payload: bytes 
