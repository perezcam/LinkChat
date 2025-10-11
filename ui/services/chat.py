import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from state.models import ChatMessage
from services.ipc_uds import UDSBridge

@dataclass
class ChatService:
    bridge: "UDSBridge"
    messages_by_mac: Dict[str, List[ChatMessage]] = field(default_factory=dict)

    #helpers
    def _now_hhmm(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _append(self, mac: str, msg: ChatMessage):
        self.messages_by_mac.setdefault(mac, []).append(msg)

    def _send_cmd(self, cmd: dict):
        # Mantén una única puerta de salida hacia el IPC.
        asyncio.run(self.bridge.send_cmd(cmd))

    #  Eventos entrantes (desde IPC) 
    def on_chat(self, evt: dict):
        mac = str(evt.get("src", ""))
        text = str(evt.get("text", ""))
        self._append(mac, ChatMessage("rx", text, self._now_hhmm()))

    #  Envío 1-a-1 
    def send_text(self, dst_mac: str, text: str):
        # eco local 
        self._append(dst_mac, ChatMessage("tx", text, self._now_hhmm()))
        # envío por IPC
        self._send_cmd({"type": "send_text", "dst": dst_mac, "body": text})

    #  Envío a TODOS 
    def send_text_all(self, text: str, *, active_since: Optional[float] = None, echo: bool = False):
        """
        Envía 'text' a todos los vecinos activos. Si 'active_since' se especifica (seg),
        el backend filtrará por last_seen <= active_since (por defecto 60s en AppServer).
        Si 'echo' es True, agrega el mensaje en el hilo "__ALL__" localmente.
        """
        if echo:
            self._append("__ALL__", ChatMessage("tx", text, self._now_hhmm()))

        cmd = {"type": "send_text_all", "body": text}
        if isinstance(active_since, (int, float)) and active_since >= 0:
            cmd["active_since"] = float(active_since)

        self._send_cmd(cmd)
