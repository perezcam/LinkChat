# imports existentes
import queue
import threading
import time
from typing import Callable, Dict, Any, Optional, List

from raw_socket import SocketManager
from src.network.enums.enums import MessageType
from src.network.frame_creator import create_ethernet_frame
from src.network.frame_decoder import decode_ethernet_frame

BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"

class ServiceThreads:
    def __init__(self, sock: SocketManager, src_mac: str, alias: str = "Anon"):
        self.sock = sock
        self.src_mac = src_mac                   # string "aa:bb:…"
        self.alias = alias                       # alias local
        self.in_queue = queue.Queue(maxsize=1024)
        self.out_queue = queue.Queue(maxsize=1024)
        self.stop_evt = threading.Event()

        # despacho y timers
        self.handlers = {}       # MessageType -> callable
        self.timers = {}         # name -> next_fire_epoch
        self.timer_periods = {}  # name -> seconds

        # = tabla de vecinos =
        # key: mac str "aa:bb:…", value: {"alias": str, "last_seen": float}
        self.neighbors: Dict[str, Dict[str, Any]] = {}

        # opcional: callback cuando cambie vecinos
        self.on_neighbors_changed: Optional[Callable[[Dict[str, Dict[str, Any]]], None]] = None

        # secuencia simple para creator
        self._seq = 0

        # threads
        self.rx_t = threading.Thread(target=self._rx_loop, name="rx", daemon=True)
        self.tx_t = threading.Thread(target=self._tx_loop, name="tx", daemon=True)
        self.tp_t = threading.Thread(target=self._timer_pump, name="timers", daemon=True)
        self.dp_t = threading.Thread(target=self._dispatch_loop, name="dispatch", daemon=True)

        # registrar handlers de discovery ===
        self.register_handler(MessageType.DISCOVER_REPLY, self._handle_discover_reply)

    # ---------- API pública ----------
    def start(self):
        self.rx_t.start()
        self.tx_t.start()
        self.dp_t.start()
        self.tp_t.start()

        # timer de descubrimiento (cada 5 s) ===
        self.add_timer("discover", period_seconds=5.0)

    def stop(self):
        self.stop_evt.set()

    def register_handler(self, msg_type: MessageType, fn: Callable[[dict], None]):
        self.handlers[msg_type] = fn

    def add_timer(self, name: str, period_seconds: float):
        now = time.time()
        self.timers[name] = now + period_seconds
        self.timer_periods[name] = period_seconds

    # Permite a la app suscribirse a cambios en vecinos
    def set_on_neighbors_changed(self, cb: Callable[[Dict[str, Dict[str, Any]]], None]):
        self.on_neighbors_changed = cb

    # ---------- Loops ----------
    def _rx_loop(self):
        while not self.stop_evt.is_set():
            try:
                frame = self.sock.receive_raw_frame() 
                if not frame:
                    continue
                msg = decode_ethernet_frame(frame)  # dict: dst_mac, src_mac, message_type, sequence, payload
                self.in_queue.put(msg)
            except Exception as e:
                print(f"[rx] error: {e}")
                time.sleep(0.05)

    def _tx_loop(self):
        while not self.stop_evt.is_set():
            try:
                item = self.out_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                # item puede ser frame crudo o dict de parámetros
                if isinstance(item, (bytes, bytearray)):
                    self.sock.send_raw_frame(item)    
                elif isinstance(item, dict):
                    frame = create_ethernet_frame(
                        src_mac=item["src_mac"],
                        dst_mac=item["dst_mac"],
                        payload=item["payload"],
                        message_type=item["message_type"],
                        sequence=item["sequence"],
                        ether_type=self.sock.ethertype
                    )
                    self.sock.send_raw_frame(frame)
                else:
                    print("[tx] item desconocido:", type(item))
            except Exception as e:
                print(f"[tx] error: {e}")

    def _dispatch_loop(self):
        while not self.stop_evt.is_set():
            try:
                msg = self.in_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                mtype = msg.get("message_type")
                handler = self.handlers.get(mtype)
                if handler:
                    handler(msg)
                # Si llega un DISCOVER_REQUEST a este nodo, respóndele
                if mtype == MessageType.DISCOVER_REQUEST:
                    self._reply_discover(msg)
            except Exception as e:
                print(f"[dispatch] error: {e}")

    def _timer_pump(self):
        while not self.stop_evt.is_set():
            now = time.time()
            fired = [name for name, tnext in self.timers.items() if now >= tnext]
            for name in fired:
                self.timers[name] = now + self.timer_periods[name]
                cb = getattr(self, f"_timer_cb_{name}", None)
                if cb:
                    try:
                        cb()
                    except Exception as e:
                        print(f"[timer {name}] error: {e}")
            time.sleep(0.05)

    # ---------- Timers & Handlers específicos ----------
    def _timer_cb_discover(self):
        """Envia DISCOVER_REQUEST por broadcast con el alias local."""
        self._seq = (self._seq + 1) & 0xFFFF
        payload = f"alias={self.alias}"
        self.out_queue.put({
            "src_mac": self.src_mac,
            "dst_mac": BROADCAST_MAC,
            "payload": payload,
            "message_type": MessageType.DISCOVER_REQUEST,
            "sequence": self._seq,
        })
        # print(f"[discover] request seq={self._seq} alias='{self.alias}'")

    def _reply_discover(self, req_msg: dict):
        """Responde unicast con DISCOVER_REPLY (incluye mi alias)."""
        src = req_msg["src_mac"]  # mac string del emisor
        self._seq = (self._seq + 1) & 0xFFFF
        payload = f"alias={self.alias}"
        self.out_queue.put({
            "src_mac": self.src_mac,
            "dst_mac": src,
            "payload": payload,
            "message_type": MessageType.DISCOVER_REPLY,
            "sequence": self._seq,
        })
        # print(f"[discover] reply -> {src} alias='{self.alias}'")

    def _handle_discover_reply(self, msg: dict):
        """Actualiza tabla de vecinos con MAC + alias del vecino."""
        mac = msg["src_mac"]              # string "aa:bb:…"
        alias = self._parse_alias(msg.get("payload", ""))
        now = time.time()

        entry = self.neighbors.get(mac)
        if entry and entry.get("alias") == alias:
            # solo refresca last_seen
            entry["last_seen"] = now
        else:
            self.neighbors[mac] = {"alias": alias, "last_seen": now}
            print(f"[neighbors] {mac} -> alias='{alias}'")

        if self.on_neighbors_changed:
            try:
                self.on_neighbors_changed(self.neighbors)
            except Exception as e:
                print(f"[neighbors cb] error: {e}")

    # ---------- Utilidades ----------
    @staticmethod
    def _parse_alias(payload: str) -> str:
        # payload formato: "alias=Nombre Con Espacios"
        if payload.startswith("alias="):
            return payload[6:].strip()
        return payload.strip()
