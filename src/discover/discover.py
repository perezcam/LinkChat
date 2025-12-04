import time
from typing import Callable, Dict, Any, Optional
from src.core.managers.service_threads import ThreadManager
from src.core.schemas.frame_schemas import FrameSchema, HeaderSchema
from src.core.schemas.scheduled_task import ScheduledTask
from src.core.enums.enums import MessageType
from src.prepare.network_config import get_ether_type


class Discovery:
    BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"

    def __init__(self, service_threads: ThreadManager, alias: str, interval_seconds: float = 5.0):
        self._attached = False
        self.service_threads = service_threads
        self.alias = alias
        self.interval = interval_seconds

        self.neighbors: Dict[str, Dict[str, Any]] = {}

        self.src_mac = self.service_threads.src_mac

        #Callback para detectar cambios en la tabla de vecinos
        self.on_neighbors_changed: Optional[Callable[[Dict[str, Dict[str, Any]]], None]] = None

        self._seq: int = 0

    #  Registro en ThreadManager 
    def attach(self):
        """
        Registra los handlers y agenda la tarea periódica de discover.
        """
        if self._attached:
            return
        self._attached = True

        self.service_threads.add_message_handler(MessageType.DISCOVER_REQUEST, self._on_discover_request)
        self.service_threads.add_message_handler(MessageType.DISCOVER_REPLY, self._on_discover_reply)

        self.service_threads.add_scheduled_task(
            ScheduledTask(action=self._timer_cb_discover, interval=self.interval)
        )

    def detach(self):
        """
        Quitar handlers y tareas para desmontar discovery
        """
        self.service_threads.remove_message_handler(MessageType.DISCOVER_REQUEST)
        self.service_threads.remove_message_handler(MessageType.DISCOVER_REPLY)
        self.service_threads.remove_scheduled_task(self._timer_cb_discover)
        
  
    #  API externa 
    def set_on_neighbors_changed(self, cb: Callable[[Dict[str, Dict[str, Any]]], None]):
        self.on_neighbors_changed = cb

    #  Timer: enviar discover 
    def _timer_cb_discover(self):
        """Envía DISCOVER_REQUEST por broadcast con el alias local."""
        self._seq = (self._seq + 1) & 0xFFFF
        payload = f"alias={self.alias}"

        payload_bytes = payload.encode("utf-8") 
        frame = FrameSchema(
            src_mac=self.src_mac,
            dst_mac=self.BROADCAST_MAC,
            ethertype=get_ether_type(),
            header=HeaderSchema(
                message_type=MessageType.DISCOVER_REQUEST,
                sequence=self._seq,
                payload_len=len(payload_bytes),
            ),
            payload=payload_bytes, 
        )

        self.service_threads.queue_frame_for_sending(frame)

    #  Handlers de recepción 
    def _on_discover_request(self, frame: FrameSchema):
        """
        Responde unicast con DISCOVER_REPLY cuando otro nodo hace DISCOVER_REQUEST.
        """
      
        mac_origen = frame.src_mac

        self._seq = (self._seq + 1) & 0xFFFF
        payload = f"alias={self.alias}"
        payload_bytes = payload.encode("utf-8")

        reply = FrameSchema(
            src_mac=self.src_mac,
            dst_mac=mac_origen,
            ethertype=get_ether_type(),
            header= HeaderSchema(
                message_type=MessageType.DISCOVER_REPLY,
                sequence=self._seq,
                payload_len=len(payload_bytes)
            ),
            payload=payload_bytes
        )
        self.service_threads.queue_frame_for_sending(reply)

    def _on_discover_reply(self, frame: FrameSchema):
        """
        Actualiza la tabla de vecinos cuando llega un DISCOVER_REPLY.
        """

        mac_vecino = frame.src_mac
        payload_bytes = frame.payload

        payload_str = payload_bytes.decode("utf-8")
        alias = self._parse_alias(payload_str)
        now = time.time()

        entry = self.neighbors.get(mac_vecino)
        if entry and entry.get("alias") == alias:
            entry["last_seen"] = now
        else:
            self.neighbors[mac_vecino] = {"alias": alias, "last_seen": now}

        if self.on_neighbors_changed:
            try:
                self.on_neighbors_changed(self.neighbors)
            except Exception as e:
                
                print(f"[neighbors cb] error: {e}")

    #  Utilidades 
    @staticmethod
    def _parse_alias(payload: str) -> str:
        # payload formato: "alias=Nombre Con Espacios"
        if payload.startswith("alias="):
            return payload[6:].strip()
        return payload.strip()
