from enum import Enum, auto

class MessageType(Enum):
    DISCOVER_REQUEST = auto()
    DISCOVER_REPLY   = auto()
    APP_MESSAGE = auto()
    ACK = auto()     # Message type for confirmation
    FILE_META = auto()
    FILE_DATA = auto()   
    FILE_FIN = auto() 



