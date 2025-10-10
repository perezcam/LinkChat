from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Contact:
    mac: str
    name: str = "Contacto"
    online: bool = False
    last_msg: str = ""
    last_time: str = ""

@dataclass
class ChatMessage:
    side: str   # 'tx' or 'rx'
    text: str
    time: str = ""

@dataclass
class AppState:
    contacts: List[Contact] = field(default_factory=list)
    by_mac_msgs: Dict[str, List[ChatMessage]] = field(default_factory=dict)
    selected_mac: str | None = None

    def ensure_chat(self, mac: str):
        self.by_mac_msgs.setdefault(mac, [])
