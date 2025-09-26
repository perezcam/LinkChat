import time
from typing import Callable, Dict, Any, Optional
from src.core.managers.service_threads import ThreadManager
from src.core.schemas.frame_schemas import FrameSchema
from src.core.schemas.scheduled_task import ScheduledTask
from src.core.enums.enums import MessageType

class Discovery:
    BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"

    def __init__(self, service_threads: ThreadManager, alias: str, interval_seconds: float = 5.0):
        self.service_threads = service_threads
        self.alias = alias
        self.interval = interval_seconds

        # Tabla de vecinos: mac -> {"alias": str, "last_seen": epoch}
        self.neighbors: Dict[str, Dict[str, Any]] = {}

        # MAC local
        self.src_mac = self.service_threads.src_mac

        # Callback opcional si la app quiere enterarse de cambios
        self.on_neighbors_changed: Optional[Callable[[Dict[str, Dict[str, Any]]], None]] = None

        # Contador de secuencia
        self._seq: int = 0

    # -------------- Registro en ThreadManager --------------
    def attach(self):
        """
        Registra los handlers y agenda la tarea periódica de discover.
        Llamar después de que ThreadManager haya abierto el socket y seteado src_mac.
        """

        # Registra handlers
        self.service_threads.message_handlers[MessageType.DISCOVER_REQUEST] = self._on_discover_request
        self.service_threads.message_handlers[MessageType.DISCOVER_REPLY]   = self._on_discover_reply

        # Agenda tarea periódica para enviar DISCOVER_REQUEST
        self.service_threads.scheduled_tasks.append(
            ScheduledTask(action=self._timer_cb_discover, interval=self.interval, last_run=0.0)
        )

    def detach(self):
        """
        (Opcional) Quita handlers y tareas si necesitas desmontar Discovery.
        """
        self.service_threads.message_handlers.pop(MessageType.DISCOVER_REQUEST, None)
        self.service_threads.message_handlers.pop(MessageType.DISCOVER_REPLY, None)
        self.service_threads.scheduled_tasks = [
            t for t in self.service_threads.scheduled_tasks if t.action is not self._timer_cb_discover
        ]
    #TODO #para detectar eventos desp si queremos saber cuando detectamos a alguien nuevo actualizar la tabla visual de la app
    # -------------- API externa --------------
    def set_on_neighbors_changed(self, cb: Callable[[Dict[str, Dict[str, Any]]], None]):
        self.on_neighbors_changed = cb

    # -------------- Timer: enviar discover --------------
    def _timer_cb_discover(self):
        """Envía DISCOVER_REQUEST por broadcast con el alias local."""
        self._seq = (self._seq + 1) & 0xFFFF
        payload = f"alias={self.alias}"

        frame = FrameSchema(
            src_mac=self.src_mac,
            dst_mac=self.BROADCAST_MAC,
            payload=payload,
            message_type=MessageType.DISCOVER_REQUEST,
            sequence=self._seq,
        )
        self.service_threads.queue_frame_for_sending(frame)

    # -------------- Handlers de recepción --------------
    def _on_discover_request(self, frame: FrameSchema):
        """
        Responde unicast con DISCOVER_REPLY cuando otro nodo hace DISCOVER_REQUEST.
        """
      
        mac_origen = getattr(frame.header, "src_mac", None) or getattr(frame, "src_mac", None)
        if not mac_origen:
            return  # no hay destino válido

        self._seq = (self._seq + 1) & 0xFFFF
        payload = f"alias={self.alias}"

        reply = FrameSchema(
            src_mac=self.src_mac,
            dst_mac=mac_origen,
            payload=payload,
            message_type=MessageType.DISCOVER_REPLY,
            sequence=self._seq,
        )
        self.service_threads.queue_frame_for_sending(reply)

    def _on_discover_reply(self, frame: FrameSchema):
        """
        Actualiza la tabla de vecinos cuando llega un DISCOVER_REPLY.
        """
     
        mac_vecino = getattr(frame.header, "src_mac", None) or getattr(frame, "src_mac", None)
        payload = getattr(frame, "payload", "")  # cadena "alias=Nombre"
        if not mac_vecino:
            return

        alias = self._parse_alias(payload)
        now = time.time()

        entry = self.neighbors.get(mac_vecino)
        if entry and entry.get("alias") == alias:
            entry["last_seen"] = now
        else:
            self.neighbors[mac_vecino] = {"alias": alias, "last_seen": now}
            print(f"[neighbors] {mac_vecino} -> alias='{alias}'")

        if self.on_neighbors_changed:
            try:
                self.on_neighbors_changed(self.neighbors)
            except Exception as e:
                
                print(f"[neighbors cb] error: {e}")

    # -------------- Utilidades --------------
    @staticmethod
    def _parse_alias(payload: str) -> str:
        # payload formato: "alias=Nombre Con Espacios"
        if payload.startswith("alias="):
            return payload[6:].strip()
        return payload.strip()
