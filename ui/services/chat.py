import asyncio
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime
from state.models import ChatMessage
from services.ipc_uds import UDSBridge

@dataclass
class ChatService:
    bridge: "UDSBridge"
    messages_by_mac: Dict[str, List[ChatMessage]] = field(default_factory=dict)

    def on_chat(self, evt: dict):
        mac = str(evt.get("src",""))
        text = str(evt.get("text",""))
        self._append(mac, ChatMessage("rx", text, datetime.now().strftime("%H:%M")))

    def send_text(self, dst_mac: str, text: str):
        self._append(dst_mac, ChatMessage("tx", text, datetime.now().strftime("%H:%M")))
        asyncio.run(self.bridge.send_cmd({"type":"send_text","dst":dst_mac,"body":text}))

    def _append(self, mac, msg: ChatMessage):
        self.messages_by_mac.setdefault(mac, []).append(msg)
