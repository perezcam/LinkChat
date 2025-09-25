from enum import Enum, auto

class MessageType(Enum):
    HELLO = 0x01   # Mesage type for discovery
    DATA = 0x02    # Message type for data transfer
    ACK = 0x03     # Message type for confirmation
    FILE = 0x04    # Message type for file transfer
    FILE_END = 0x05 # Message type that indicates the end of a file transfer
    DISCOVER_REQUEST = auto()
    DISCOVER_REPLY   = auto()

