import os
import sys
import time
import json
import asyncio
import logging
import signal
import threading
import contextlib
from typing import Optional, Dict, Any

from src.messaging.service_messaging import Messaging
from src.core.managers.raw_socket import SocketManager
from src.core.managers.service_threads import ThreadManager
from src.discover.discover import Discovery
from src.prepare.network_config import get_runtime_config
from src.file_transfer.handlers.file_transfer_handler import FileTransferHandler
from src.file_transfer.file_sender import FileSender
from src.file_transfer.file_receiver import FileReceiver
from src.security.security_handler import SecurityHandler
from src.security.security_manager import SecurityManager

# <<< NUEVO: bus de eventos RX para la UI >>>
from src.file_transfer.handlers.ui_events import set_sinks

try:
    from ipc.ipc_server import IPCServer
    _IPC_AVAILABLE = True
except Exception:
    _IPC_AVAILABLE = False

DEFAULT_SOCK_DIR = os.environ.get("IPC_DIR", "/ipc")
DEFAULT_SOCK_NAME = os.environ.get("IPC_NAME", "linkchat")
DEFAULT_BASE_DIR = os.environ.get("BASE_DIR", "/shared")


def _neighbors_snapshot(neighbors: Dict[str, Dict[str, Any]]):
    now = time.time()
    rows = []
    for mac, meta in list(neighbors.items()):
        rows.append({
            "mac": mac,
            "alias": meta.get("alias", "?"),
            "last_seen_ms": int(1000 * max(0.0, now - meta.get("last_seen", 0.0))),
        })
    return {"type": "neighbors_changed", "rows": rows}


def _resolve_socket_path(alias: str) -> str:
    fname = f"{DEFAULT_SOCK_NAME}-{alias}.sock"
    return os.path.join(DEFAULT_SOCK_DIR, fname)


class AppServer:
    """
    Orquestador backend:
      - Levanta raw socket, threads, discovery, messaging, seguridad, IPC UDS.
      - Expone comandos por IPC (send_text, send_text_all, file_send, folder_send...).
      - Publica eventos a la UI: chat, vecinos y file_tx_* / file_rx_*.
    """
    def __init__(
        self,
        *,
        interface: Optional[str] = None,
        alias: Optional[str] = None,
        ethertype: Optional[int | str] = None,
        ipc_enable: Optional[bool] = None,
        socket_path: Optional[str] = None,
    ):
        cfg = get_runtime_config()

        self.interface = interface or cfg["interface"]

        self.alias = alias or cfg.get("alias") or os.environ.get("ALIAS", "Nodo-A")
        _et = ethertype if ethertype is not None else (cfg.get("ethertype") or os.environ.get("ETHER_TYPE", 0x88B5))
        if isinstance(_et, str):
            self.ethertype = int(_et, 16) if _et.lower().startswith("0x") else int(_et)
        else:
            self.ethertype = int(_et)

        if ipc_enable is None:
            ipc_enable = _IPC_AVAILABLE
        self.ipc_enable = bool(ipc_enable and _IPC_AVAILABLE)

        if socket_path:
            self.socket_path = socket_path
        else:
            self.socket_path = (
                os.environ.get("IPC_SOCKET")
                or os.environ.get("IPC_SOCKET_PATH")
                or _resolve_socket_path(self.alias)
            )

        self.sock_mgr: Optional[SocketManager] = None
        self.th_mgr: Optional[ThreadManager] = None
        self.discovery: Optional[Discovery] = None
        self.messaging: Optional[Messaging] = None
        self.file_transfer: Optional[FileTransferHandler] = None

        self.file_sender: Optional[FileSender] = None
        self.file_receiver: Optional[FileReceiver] = None
        self._files_out: Dict[str, Dict[str, Any]] = {}
        self._file_poll_thread: Optional[threading.Thread] = None

        # IPC
        self.ipc: Optional[IPCServer] = None
        self._ipc_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ipc_thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

        self.security: SecurityManager | None = None

    # ------------- IPC glue -------------
    def _emit_event(self, ev: Dict[str, Any]):
        if not (self.ipc and self._ipc_loop):
            logging.warning("[AppServer] _emit_event() omitido: IPC no inicializado")
            return
        try:
            asyncio.run_coroutine_threadsafe(self.ipc.broadcast(ev), self._ipc_loop)
        except Exception:
            logging.exception("Error emitiendo evento IPC")

    async def _on_cmd(self, cmd: Dict[str, Any]):
        try:
            t = (cmd.get("type") or cmd.get("cmd") or "").lower()
            if t in ("ping",):
                return {"pong": True, "alias": self.alias}

            if t in ("echo",):
                return {"echo": cmd.get("text", "")}

            # ---------- Envío 1-a-1 ----------
            if t in ("send_text", "send_message"):
                dst = cmd.get("dst") or cmd.get("dst_mac")
                body = cmd.get("body") if "body" in cmd else cmd.get("text", "")
                if not (dst and isinstance(body, str)):
                    return {"ok": False, "error": "missing dst/body"}
                self.messaging.send_to_mac(dst, body.encode("utf-8"))
                return {"ok": True}

            # ---------- Broadcast SOLO TEXTO ----------
            if t in ("send_text_all", "broadcast_text"):
                body = cmd.get("body") if "body" in cmd else cmd.get("text", "")
                if not isinstance(body, str):
                    return {"ok": False, "error": "body debe ser str"}
                body = body.strip()
                if not body:
                    return {"ok": False, "error": "mensaje vacío"}

                # Ventana de actividad opcional (segundos)
                active_since = cmd.get("active_since")
                if isinstance(active_since, (int, float)) and active_since >= 0:
                    window = float(active_since)
                else:
                    # por defecto, vecinos vistos en los últimos 60s (coincide con tu Messaging)
                    window = 60.0

                # Snapshot y filtro de vecinos elegibles
                neighbors = getattr(self.discovery, "neighbors", {}) or {}
                now = time.time()
                targets = [
                    mac for mac, meta in list(neighbors.items())
                    if (now - (meta or {}).get("last_seen", 0)) <= window
                ]

                # Envía usando la API ya existente
                if hasattr(self.messaging, "send_to_macs"):
                    self.messaging.send_to_macs(targets, body.encode("utf-8"))
                else:
                    # Fallback a broadcast genérico si existiese
                    if hasattr(self.messaging, "send_to_all_neighbors"):
                        self.messaging.send_to_all_neighbors(body.encode("utf-8"), only_active_since=window)
                    else:
                        return {"ok": False, "error": "Messaging no expone send_to_macs ni send_to_all_neighbors"}

                return {"ok": True, "sent": len(targets)}

            # ---------- Vecinos ----------
            if t in ("roster_get", "neighbors_get"):
                return _neighbors_snapshot(self.discovery.neighbors)

            # ---------- Envío de archivo ----------
            if t == "file_send":
                # {"type":"file_send","dst":"aa:bb:...","path":"/abs/file"}
                dst = cmd.get("dst") or cmd.get("dst_mac")
                path = cmd.get("path")
                if not (dst and path and os.path.exists(path)):
                    return {"ok": False, "error": "missing dst/path or not exists"}

                if not self.file_sender:
                    chunk_size = int(os.environ.get("CHUNK_SIZE", "1200"))
                    self.file_sender = FileSender(self.th_mgr, chunk_size)

                file_id = self.file_sender.send_file(path=path, dst_mac=dst)
                meta = {"dst": dst, "path": path, "name": os.path.basename(path), "t0": time.time()}
                self._files_out[file_id] = meta

                # Evento TX start
                self._emit_event({"type": "file_tx_started", "file_id": file_id, "dst": dst, "name": meta["name"]})
                self._ensure_file_poller()
                return {"ok": True, "file_id": file_id}

            # ---------- Envío de carpeta ----------
            if t == "folder_send":
                dst = cmd.get("dst") or cmd.get("dst_mac")
                folder = cmd.get("folder") or cmd.get("path")
                if not (dst and folder and os.path.isdir(folder)):
                    return {"ok": False, "error": "missing dst/folder or not a directory"}

                if not self.file_sender:
                    chunk_size = int(os.environ.get("CHUNK_SIZE", "900"))
                    self.file_sender = FileSender(self.th_mgr, chunk_size)

                sent_list = self.file_sender.send_folder(folder_path=folder, dst_mac=dst)
                files_resp = []
                for file_id, rel in sent_list:
                    path_abs = os.path.join(folder, rel)
                    name = os.path.basename(rel) or os.path.basename(path_abs)
                    meta = {"dst": dst, "path": path_abs, "name": name, "rel": rel, "t0": time.time()}
                    self._files_out[file_id] = meta

                    # Evento TX start con rel
                    self._emit_event({
                        "type": "file_tx_started",
                        "file_id": file_id,
                        "dst": dst,
                        "name": name,
                        "rel": rel,
                    })
                    files_resp.append({"file_id": file_id, "rel": rel})

                self._ensure_file_poller()
                return {"ok": True, "files": files_resp}

            return {"ok": False, "error": f"unknown_command:{t}"}
        except Exception as e:
            logging.exception("Error en _on_cmd")
            return {"ok": False, "error": str(e)}

    def _start_ipc(self):
        if not self.ipc_enable:
            logging.info("IPC deshabilitado o no disponible.")
            return

        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)
        self.ipc = IPCServer(self._on_cmd, socket_path=self.socket_path)

        async def chmod_when_ready(path: str):
            for _ in range(200):  # ~10 s
                await asyncio.sleep(0.05)
                with contextlib.suppress(FileNotFoundError):
                    os.chmod(path, 0o666)  # RW para todos
                    return

        def _ipc_thread_fn():
            loop = asyncio.new_event_loop()
            self._ipc_loop = loop
            asyncio.set_event_loop(loop)

            async def runner():
                await asyncio.gather(self.ipc.start(), chmod_when_ready(self.socket_path))

            try:
                loop.run_until_complete(runner())
            finally:
                with contextlib.suppress(Exception):
                    loop.stop()

        self._ipc_thread = threading.Thread(target=_ipc_thread_fn, daemon=True)
        self._ipc_thread.start()
        logging.info(f"[IPC] UDS escuchando en {self.socket_path}")

    # ------------- Backend → UI (eventos) -------------
    def _on_neighbors_changed(self, _rows_dict):
        self._emit_event(_neighbors_snapshot(self.discovery.neighbors))

    def _on_app_message(self, frame, src_mac: str, payload: bytes):
        try:
            text = payload.decode("utf-8", "ignore")
        except Exception:
            text = ""
        self._emit_event({"type": "chat", "src": src_mac, "text": text})

    def _register_file_rx_callbacks(self):
        """
        Conecta el receptor de archivos al bus de eventos global para que la UI
        reciba: file_rx_started/progress/finished/error vía IPC.
        """
        if not self.file_receiver:
            return

        def on_started(ev: Dict[str, Any]):
            self._emit_event({
                "type": "file_rx_started",
                "file_id": ev.get("file_id"),
                "src": ev.get("src"),
                "name": ev.get("name"),
                "rel": ev.get("rel"),
            })

        def on_progress(ev: Dict[str, Any]):
            self._emit_event({
                "type": "file_rx_progress",
                "file_id": ev.get("file_id"),
                "src": ev.get("src"),
                "name": ev.get("name"),
                "rel": ev.get("rel"),
                "acked": ev.get("acked"),
                "total": ev.get("total"),
                "progress": ev.get("progress"),
            })

        def on_finished(ev: Dict[str, Any]):
            self._emit_event({
                "type": "file_rx_finished",
                "file_id": ev.get("file_id"),
                "src": ev.get("src"),
                "name": ev.get("name"),
                "rel": ev.get("rel"),
                "status": ev.get("status") or "ok",
            })

        def on_error(ev: Dict[str, Any]):
            self._emit_event({
                "type": "file_rx_error",
                "file_id": ev.get("file_id"),
                "src": ev.get("src"),
                "name": ev.get("name"),
                "rel": ev.get("rel"),
                "error": ev.get("error") or "error",
            })

        # <<< NUEVO: registro de sinks globales >>>
        set_sinks(
            on_started=on_started,
            on_progress=on_progress,
            on_finished=on_finished,
            on_error=on_error,
        )

    def _ensure_file_poller(self):
        if self._file_poll_thread and self._file_poll_thread.is_alive():
            return
        self._file_poll_thread = threading.Thread(target=self._file_progress_poller, daemon=True)
        self._file_poll_thread.start()

    def _file_progress_poller(self):
        while not self._stop_evt.is_set():
            try:
                for file_id, meta in list(self._files_out.items()):
                    ctx = self.th_mgr.get_ctx_by_id(file_id) if self.th_mgr else None
                    if not ctx:
                        continue
                    acked = int(ctx.last_acked) + 1
                    total = int(ctx.total_chunks)
                    prog = (acked / total) if total else 0.0
                    self._emit_event({
                        "type": "file_tx_progress",
                        "file_id": file_id,
                        "dst": meta["dst"],
                        "name": meta["name"],
                        "rel": meta.get("rel"),
                        "acked": acked,
                        "total": total,
                        "progress": prog,
                    })
                    if getattr(ctx, "finished", False):
                        self._emit_event({
                            "type": "file_tx_finished",
                            "file_id": file_id,
                            "dst": meta["dst"],
                            "name": meta["name"],
                            "rel": meta.get("rel"),
                            "status": "ok",
                        })
                        self._files_out.pop(file_id, None)
            except Exception:
                logging.exception("file_progress_poller error")
            finally:
                time.sleep(0.2)

    # ------------- Lifecycle -------------
    def run_forever(self):
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format="%(asctime)s - %(levelname)s - [pid=%(process)d] %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
            force=True
        )
        # Señales
        with contextlib.suppress(Exception):
            signal.signal(signal.SIGINT, lambda *_: self.stop())
            signal.signal(signal.SIGTERM, lambda *_: self.stop())

        try:
            with SocketManager(interface=self.interface, ethertype=self.ethertype) as sock:
                logging.info(
                    "Socket crudo en '%s' EtherType=0x%04x MAC=%s",
                    self.interface, self.ethertype, sock.mac
                )

                self.file_transfer = FileTransferHandler(sock.mac)

                # --- Seguridad (PSK) ---
                try:
                    psk_env = os.environ.get("PSK")
                    if not psk_env:
                        raise RuntimeError("No PSK provided. Set PSK in env (bytes or hex).")

                    pe = psk_env.strip().lower()
                    try:
                        if pe.startswith("0x"):
                            psk_bytes = bytes.fromhex(pe[2:])
                        elif all(c in "0123456789abcdef" for c in pe) and (len(pe) % 2 == 0):
                            psk_bytes = bytes.fromhex(pe)
                        else:
                            psk_bytes = psk_env.encode("utf-8")
                    except Exception:
                        psk_bytes = psk_env.encode("utf-8")

                    sec_handler = SecurityHandler()
                    self.security = SecurityManager(pre_shared_key=psk_bytes, sec_handler=sec_handler)
                    logging.info("[Security] Enabled with PSK (%d bytes).", len(psk_bytes))
                except Exception as e:
                    logging.error("[Security] Failed to initialize: %s", e)
                    raise

                self.th_mgr = ThreadManager(
                    socket_manager=sock,
                    file_transfer_handler=self.file_transfer,
                    security=self.security
                )
                self.th_mgr.start()

                # RX de archivos (con callbacks a IPC por set_sinks)
                os.makedirs(DEFAULT_BASE_DIR, exist_ok=True)
                self.file_receiver = FileReceiver(self.th_mgr, DEFAULT_BASE_DIR)
                self._register_file_rx_callbacks()

                # Discovery + Messaging
                self.discovery = Discovery(service_threads=self.th_mgr, alias=self.alias, interval_seconds=5.0)
                self.discovery.attach()

                self.messaging = Messaging(threads=self.th_mgr, neighbors_ref=self.discovery.neighbors, alias=self.alias)
                self.messaging.attach()

                # hooks backend → IPC/UI
                with contextlib.suppress(Exception):
                    self.discovery.set_on_neighbors_changed(self._on_neighbors_changed)
                self.messaging.on_message(self._on_app_message)

                # IPC
                self._start_ipc()

                logging.info(
                    "AppServer listo. Alias=%s  UDS=%s",
                    self.alias,
                    self.socket_path if self.ipc_enable else "disabled"
                )
                while not self._stop_evt.is_set():
                    time.sleep(0.2)

        except PermissionError:
            logging.error("Permisos insuficientes para raw sockets.")
            sys.exit(1)
        except OSError as e:
            logging.error(f"Error al abrir el socket: {e}")
            sys.exit(1)
        except Exception:
            logging.exception("Error inesperado en AppServer")
            sys.exit(1)
        finally:
            with contextlib.suppress(Exception):
                if self.th_mgr:
                    self.th_mgr.stop()
            with contextlib.suppress(Exception):
                if self.discovery:
                    self.discovery.detach()
            with contextlib.suppress(Exception):
                if self.messaging:
                    self.messaging.detach()
            if self.ipc and self._ipc_loop:
                with contextlib.suppress(Exception):
                    asyncio.run_coroutine_threadsafe(self.ipc.stop(), self._ipc_loop)

    def stop(self):
        self._stop_evt.set()


def main():
    alias = os.environ.get("ALIAS", "Nodo-A")
    sock_path = (
        os.environ.get("IPC_SOCKET")
        or os.environ.get("IPC_SOCKET_PATH")
        or _resolve_socket_path(alias)
    )
    server = AppServer(socket_path=sock_path)
    server.run_forever()


if __name__ == "__main__":
    main()
