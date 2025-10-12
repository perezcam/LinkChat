import logging
import time
from typing import Callable, Dict, Iterable, Optional
from src.core.enums.enums import MessageType
from src.core.managers.service_threads import ThreadManager
from src.core.schemas.frame_schemas import FrameSchema, HeaderSchema
from src.prepare.network_config import get_ether_type

class Messaging:
    def __init__(self, threads: ThreadManager, neighbors_ref: Dict[str, Dict],alias: str):
        self.threads = threads
        self.neighbors = neighbors_ref
        self._seq = 0
        self._on_message: Optional[Callable[[FrameSchema, str, bytes], None]] = None
        self._attached = False

    #  ciclo de vida 
    def attach(self):
        if self._attached:
            return
       
        self.threads.add_message_handler(MessageType.APP_MESSAGE, self._on_app_message)
        self._attached = True

    def detach(self):
        if not self._attached:
            return
        self.threads.remove_message_handler(MessageType.APP_MESSAGE)
        self._attached = False

    #  envío 
    def send_to_mac(self, dst_mac: str, payload: bytes):
        self._seq = (self._seq + 1) & 0xFFFF
        frame = FrameSchema(
            src_mac=self.threads.src_mac,
            dst_mac=dst_mac,
            ethertype=get_ether_type(),
            header=HeaderSchema(
                message_type=MessageType.APP_MESSAGE,
                sequence=self._seq,
                payload_len=len(payload),
            ),
            payload=payload,
        )
        self.threads.queue_frame_for_sending(frame)

    def send_to_macs(self, dst_macs: Iterable[str], payload: bytes):
        for mac in dst_macs:
            self.send_to_mac(mac, payload)

    def send_to_all_neighbors(self, payload: bytes, only_active_since: Optional[float] = None):
        now = time.time()
        # snapshot por concurrencia
        for mac, meta in list(self.neighbors.items()):
            last_seen = meta.get("last_seen", 0)
            if only_active_since is None:
                if now - last_seen > 60:
                    continue
            else:
                if now - last_seen > only_active_since:
                    continue
            self.send_to_mac(mac, payload)

    #  recepción 
    def on_message(self, cb: Callable[[FrameSchema, str, bytes], None]):
        self._on_message = cb

    def _on_app_message(self, frame: FrameSchema):
        if self._on_message:
            try:
                self._on_message(frame, frame.src_mac, frame.payload)
            except Exception as e:
                logging.exception(f"Callback on_message lanzó una excepción: {e}")
