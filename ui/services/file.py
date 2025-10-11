import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from services.ipc_uds import UDSBridge


@dataclass
class TransferState:
    id: str                  # tid local (ej. "tx-...")
    kind: str                # "tx" | "rx"
    name: str
    size: int                # bytes totales
    done: int = 0            # bytes completados
    status: str = "pending"  # pending|running|done|error|canceled
    peer: Optional[str] = None      # mac peer
    server_id: Optional[str] = None # file_id emitido por el servidor
    acked: Optional[int] = None     # chunks
    total: Optional[int] = None     # chunks
    progress: Optional[float] = None  # 0..1, 


@dataclass
class FileService:
    bridge: "UDSBridge"
    transfers: Dict[str, TransferState] = field(default_factory=dict)

    # Mapeos auxiliares
    _tid_by_server_id: Dict[str, str] = field(default_factory=dict, init=False)
    _pending_by_name_size: Dict[Tuple[str, int], str] = field(default_factory=dict, init=False)

    #  Suscripción a eventos del backend 
    def register_event_handlers(self, pump) -> None:
        """Conecta handlers al EventPump de la UI."""
        # TX
        pump.subscribe("file_tx_started", self._on_tx_started)
        pump.subscribe("file_tx_progress", self._on_tx_progress)
        pump.subscribe("file_tx_finished", self._on_tx_finished)
        # RX (si el servidor emite estos)
        pump.subscribe("file_rx_started", self._on_rx_started)
        pump.subscribe("file_rx_progress", self._on_rx_progress)
        pump.subscribe("file_rx_finished", self._on_rx_finished)
        # Ofertas (si hay fase de oferta/aceptación)
        pump.subscribe("file_offer", self.on_file_offer)

    #  API de envío 
    def send_path(self, dst_mac: str, path: str):
        """Si es carpeta -> folder_send; si es archivo -> file_send."""
        if os.path.isdir(path):
            return self.send_folder(dst_mac, path)
        return self.send_file(dst_mac, path)

    def send_folder(self, dst_mac: str, folder_path: str):
        """
        Envía una carpeta completa (secuencial) usando el comando IPC 'folder_send'.
        No se crea TransferState único para la carpeta: cada archivo generará sus
        propios eventos file_tx_* que este servicio ya maneja.
        """
        if not os.path.isdir(folder_path):
            raise ValueError(f"Ruta no es carpeta: {folder_path}")

        tid = f"fx-{int(time.time()*1000)}" 
        payload = {"type": "folder_send", "dst": dst_mac, "folder": folder_path, "client_tid": tid}
        fut = self.bridge.send_cmd_threadsafe(payload)

        def _done(f):
            try:
                _ = f.result()
            except Exception:
                pass
        fut.add_done_callback(_done)

        return tid

    def send_file(self, dst_mac: str, path: str):
        """
        Dispara el envío y crea el estado local inmediatamente.
        No usa asyncio en este hilo: delega el envío al loop del bridge.
        """
        name = os.path.basename(path)
        size = os.path.getsize(path)
        tid = f"tx-{int(time.time()*1000)}"

        self.transfers[tid] = TransferState(
            id=tid, kind="tx", name=name, size=size, status="running", peer=dst_mac
        )
        # Correlador por (name, size) para mapear eventos que no traen id
        self._pending_by_name_size[(name, size)] = tid

        payload = {"type": "file_send", "dst": dst_mac, "path": path, "client_tid": tid}
        fut = self.bridge.send_cmd_threadsafe(payload)

        # No esperamos respuesta RPC; los eventos de progreso/fin nos mapearán el file_id.
        # Aun así, registramos errores de envío (conexión caída, etc.).
        def _done(f):
            try:
                _ = f.result()  # None si fue OK
            except Exception:
                st = self.transfers.get(tid)
                if st and st.status == "running":
                    st.status = "error"
        fut.add_done_callback(_done)

        return tid

    #  Handlers de eventos TX 
    def _on_tx_started(self, evt: dict):
        server_id = evt.get("file_id") or evt.get("id")
        name = evt.get("name") or evt.get("filename") or ""
        size = _to_int(evt.get("size"), 0)
        peer = evt.get("dst") or evt.get("peer")

        # Buscar por id de servidor o por (name,size)
        tid = self._tid_by_server(server_id) or self._tid_by_name_size(name, evt)
        if not tid:
            tid = f"tx-{int(time.time()*1000)}"
            self.transfers[tid] = TransferState(id=tid, kind="tx", name=name, size=size)

        st = self.transfers[tid]
        st.status = "running"
        st.peer = st.peer or peer
        if size and not st.size:
            st.size = size
        if server_id:
            st.server_id = server_id
            self._tid_by_server_id[server_id] = tid

    def _on_tx_progress(self, evt: dict):
        tid = self._tid_from_evt(evt, prefer_server=True) or self._tid_by_name_size(evt.get("name"), evt)
        if not tid or tid not in self.transfers:
            return
        st = self.transfers[tid]
        st.status = "running"
        st.acked = _to_int(evt.get("acked"), st.acked)
        st.total = _to_int(evt.get("total"), st.total)
        st.progress = _to_float(evt.get("progress"), st.progress)

        if "bytes" in evt:
            st.done = max(st.done, int(evt["bytes"]))
        elif st.total and st.total > 0 and st.size:
            st.done = max(st.done, int((st.acked or 0) / st.total * st.size))
        elif st.progress is not None and st.size:
            st.done = max(st.done, int(st.progress * st.size))

    def _on_tx_finished(self, evt: dict):
        tid = self._tid_from_evt(evt, prefer_server=True) or self._tid_by_name_size(evt.get("name"), evt)
        if not tid or tid not in self.transfers:
            return
        st = self.transfers[tid]
        ok = evt.get("ok")
        status = evt.get("status")
        st.status = "done" if (ok is True or status == "ok") else "error"
        self._cleanup_tid_correlators(st)

    #  Handlers de eventos RX 
    def _on_rx_started(self, evt: dict):
        server_id = evt.get("file_id") or evt.get("id")
        name = evt.get("name") or evt.get("filename") or ""
        size = int(evt.get("size", 0))
        peer = evt.get("src") or evt.get("peer")

        tid = f"rx-{server_id or int(time.time()*1000)}"
        self.transfers[tid] = TransferState(
            id=tid, kind="rx", name=name, size=size, status="running", peer=peer, server_id=server_id
        )
        if server_id:
            self._tid_by_server_id[server_id] = tid

    def _on_rx_progress(self, evt: dict):
        tid = self._tid_from_evt(evt, prefer_server=True)
        if not tid or tid not in self.transfers:
            return
        st = self.transfers[tid]
        st.status = "running"
        st.acked = _to_int(evt.get("acked"), st.acked)
        st.total = _to_int(evt.get("total"), st.total)
        st.progress = _to_float(evt.get("progress"), st.progress)

        if "bytes" in evt:
            st.done = max(st.done, int(evt["bytes"]))
        elif st.total and st.total > 0 and st.size:
            st.done = max(st.done, int((st.acked or 0) / st.total * st.size))
        elif st.progress is not None and st.size:
            st.done = max(st.done, int(st.progress * st.size))

    def _on_rx_finished(self, evt: dict):
        tid = self._tid_from_evt(evt, prefer_server=True)
        if not tid or tid not in self.transfers:
            return
        st = self.transfers[tid]
        ok = evt.get("ok")
        status = evt.get("status")
        st.status = "done" if (ok is True or status == "ok") else "error"
        self._cleanup_tid_correlators(st)

    #  Ofertas - aceptación 
    def on_file_offer(self, evt: dict):
        """Auto-aceptación opcional (si tu backend lo requiere)."""
        offer_id = evt.get("id") or evt.get("file_id")
        auto_accept = os.environ.get("FILE_AUTO_ACCEPT", "1") == "1"
        if auto_accept and offer_id:
            self.bridge.send_cmd_threadsafe({"type": "file_accept", "id": offer_id})

    #  Utilidades 
    def _tid_from_evt(self, evt: dict, *, prefer_server: bool = True) -> Optional[str]:
        server_id = evt.get("file_id") or evt.get("id")
        if prefer_server and server_id and server_id in self._tid_by_server_id:
            return self._tid_by_server_id[server_id]
        name = evt.get("name") or evt.get("filename")
        return self._tid_by_name_size(name, evt)

    def _tid_by_server(self, server_id: Optional[str]) -> Optional[str]:
        if server_id and server_id in self._tid_by_server_id:
            return self._tid_by_server_id[server_id]
        return None

    def _tid_by_name_size(self, name: Optional[str], evt: dict) -> Optional[str]:
        if not name:
            return None
        size = _to_int(evt.get("size"), None)
        if size is None:
            # fallback por nombre si es único
            candidates = [k for k in self._pending_by_name_size.keys() if k[0] == name]
            if len(candidates) == 1:
                return self._pending_by_name_size[candidates[0]]
            return None
        key = (name, int(size))
        return self._pending_by_name_size.get(key)

    def _cleanup_tid_correlators(self, st: TransferState):
        self._pending_by_name_size.pop((st.name, st.size), None)
        if st.server_id:
            self._tid_by_server_id.pop(st.server_id, None)


#  helpers 
def _to_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default

def _to_float(v, default=None):
    try:
        return float(v)
    except Exception:
        return default
