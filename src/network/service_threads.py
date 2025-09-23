
import queue
import threading
import time
from typing import Callable
from raw_socket import SocketManager
from src.network.enums.enums import MessageType
from src.network.frame_creator import _create_header, create_ethernet_frame
from src.network.frame_decoder import decode_ethernet_frame


class ServiceThreads: 
    def __init__(self, sock: SocketManager, src_mac: str):
        self.sock = sock
        self.src_mac = src_mac
        self.in_queue = queue.Queue(maxsize=1024)
        self.out_queue = queue.Queue(maxsize=1024)
        self.stop_evt = threading.Event()
        self.handlers = {}
        self.timers = {}
        self.timer_periods = {}

        self.rx_t = threading.Thread(target=self._rx_loop, name="rx", daemon=True)
        self.tx_t = threading.Thread(target=self._tx_loop, name="tx", daemon=True)
        self.tp_t = threading.Thread(target=self._timer_pump, name="timers", daemon=True)
        self.dp_t = threading.Thread(target=self._dispatch_loop, name="dispatch", daemon=True)


    def start(self):
        self.sock.create_raw_socket()
        self.rx_t.start()
        self.tx_t.start()
        self.tp_t.start()
        self.dp_t.start()

    def stop(self):
        self.stop_evt.set()
        self.sock.close_socket()

    def on(self, mtype: MessageType, handler: Callable[[InboundMessage], None]):
        self.handlers[mtype] = handler

    def every(self, name: str, period_sec: float, fn: Callable[[], None]):
        self.timer_periods[name] = period_sec
        self.timers[name] = fn

    # --- Loops ---
    def _rx_loop(self):
        while not self.stop_evt.is_set():
            try:
                frame = self.sock.receive_raw_frame()
                if frame:
                    decoded = decode_ethernet_frame(frame)
                    msg = InboundMessage(
                        src_mac=decoded["src_mac"],
                        dst_mac=decoded["dst_mac"],
                        mtype=MessageType(decoded["message_type"]),
                        seq=decoded["sequence"],
                        payload=decoded["payload"]
                    )
                    self.in_queue.put(msg)
            except Exception as e:
                print(f"[rx] error: {e}")

    def _tx_loop(self):
        while not self.stop_evt.is_set():
            try:
                out = self.out_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                frame = create_ethernet_frame(
                    src_mac=self.src_mac,
                    dst_mac=out.dst_mac,
                    payload=out.payload,
                    message_type=out.message_type,
                    sequence=out.sequence,
                    ether_type=out.ether_type,
                )
                self.sock.send_raw_frame(frame)
            except Exception as e:
                print(f"[tx] error sending: {e}")

    def _dispatch_loop(self):
        while not self.stop_evt.is_set():
            try:
                msg = self.in_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            handler = self.handlers.get(msg.mtype)
            if handler:
                try:
                    handler(msg)
                except Exception as e:
                    print(f"[dispatch] handler {msg.mtype} failed: {e}")
            else:
                pass

    //TODO: ARREGLAR ESTO
    def _timer_pump(self):
        while not self.stop_evt.is_set():
            now = time.time()
            fired = []
            for name, tnext in self.timers.items():
                if now >= tnext:
                    fired.append(name)
                    self.timers[name] = now + self.timer_periods[name]
            for name in fired:
                cb = getattr(self, f"_timer_cb_{name}", None)
                if cb:
                    try:
                        cb()
                    except Exception as e:
                        print(f"[timer {name}] error: {e}")
            time.sleep(0.05)