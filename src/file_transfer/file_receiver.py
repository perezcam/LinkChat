import logging
import os
import pathlib
from typing import Dict, Callable, Optional

from src.core.enums.enums import MessageType
from src.core.managers.service_threads import ThreadManager
from src.core.schemas.frame_schemas import FrameSchema
from src.file_transfer.helpers.get_file_hash import get_file_hash
from src.file_transfer.helpers.parse_payload import parse_payload
from src.file_transfer.schemas.recv_ctx import FileRcvCtxSchema


class FileReceiver:
    """
    Recibe archivos, verifica integridad y los guarda en base_dir.
    Expone 'register_event_handlers' para que el orquestador
    publique eventos hacia la UI (file_rx_started/progress/finished/error).

    Cambios clave:
    - Soporta carpetas: usa kv['rel'] o kv['path'] para construir la ruta.
    - Sanitiza paths relativos para evitar traversal.
    - Crea la jerarquía de carpetas en destino.
    - Propaga 'rel' consistente en todos los eventos.
    """
    def __init__(self, service_threads: ThreadManager, base_dir: str) -> None:
        self._service_threads = service_threads
        self.ctx_by_id: Dict[str, FileRcvCtxSchema] = {}
        self.base_dir = os.path.abspath(base_dir)

        # Callbacks opcionales
        self._cb_started: Optional[Callable[[dict], None]] = None
        self._cb_progress: Optional[Callable[[dict], None]] = None
        self._cb_finished: Optional[Callable[[dict], None]] = None
        self._cb_error: Optional[Callable[[dict], None]] = None

        os.makedirs(self.base_dir, exist_ok=True)

        self._service_threads.add_message_handler(MessageType.FILE_DATA, self._on_data)
        self._service_threads.add_message_handler(MessageType.FILE_META, self._on_meta)

    # ---------- API de callbacks para AppServer ----------
    def register_event_handlers(
        self,
        on_started: Callable[[dict], None] | None = None,
        on_progress: Callable[[dict], None] | None = None,
        on_finished: Callable[[dict], None] | None = None,
        on_error: Callable[[dict], None] | None = None,
    ):
        self._cb_started = on_started
        self._cb_progress = on_progress
        self._cb_finished = on_finished
        self._cb_error = on_error

    # ---------- Helpers internos ----------
    def _emit_started(self, *, file_id: str, src: str, name: str, rel: str | None):
        if self._cb_started:
            try:
                self._cb_started({"file_id": file_id, "src": src, "name": name, "rel": rel})
            except Exception:
                logging.exception("[FileReceiver] Error en callback started")

    def _emit_progress(self, *, file_id: str, src: str, name: str, rel: str | None,
                       acked: int, total: int, progress: float):
        if self._cb_progress:
            try:
                self._cb_progress({
                    "file_id": file_id, "src": src, "name": name, "rel": rel,
                    "acked": acked, "total": total, "progress": progress
                })
            except Exception:
                logging.exception("[FileReceiver] Error en callback progress")

    def _emit_finished(self, *, file_id: str, src: str, name: str, rel: str | None, status: str):
        if self._cb_finished:
            try:
                self._cb_finished({"file_id": file_id, "src": src, "name": name, "rel": rel, "status": status})
            except Exception:
                logging.exception("[FileReceiver] Error en callback finished")

    def _emit_error(self, *, file_id: str, src: str | None, name: str | None, rel: str | None, error: str):
        if self._cb_error:
            try:
                self._cb_error({"file_id": file_id, "src": src, "name": name, "rel": rel, "error": error})
            except Exception:
                logging.exception("[FileReceiver] Error en callback error")

    def _send_ack(self, file_id: str, dst_mac: str, next_needed: int):
        payload = f"file_id={file_id}\nnext_needed={next_needed}\n".encode("utf-8")
        frame = self._service_threads.file_transfer_handler.get_frame(
            dst_mac, MessageType.ACK, payload
        )
        self._service_threads.queue_frame_for_sending(frame)

    def _send_fin(self, file_id: str, dst_mac: str, status: str, reason: str = ""):
        ctx = self.ctx_by_id.get(file_id)
        if not ctx:
            kv = f"file_id={file_id}\nstatus={status}\n"
            if reason:
                kv += f"reason={reason}\n"
            frame = self._service_threads.file_transfer_handler.get_frame(
                dst_mac, MessageType.FILE_FIN, kv.encode("utf-8")
            )
        else:
            frame = self._service_threads.file_transfer_handler.receiver_get_file_fin_frame(
                dst_mac=dst_mac,
                file_id=file_id,
                status=status,
                reason=reason,
            )
        self._service_threads.queue_frame_for_sending(frame)

    def _sanitize_relative_path(self, raw_path: str | None) -> str | None:
        """Acepta None, '', 'rel' o 'path' y devuelve un path relativo seguro o None."""
        if not raw_path:
            return None
        # Normalizamos como posix para interoperar entre plataformas
        path_obj = pathlib.PurePosixPath(raw_path)
        # Rechazar absolutos o segmentos vacíos / '..'
        if path_obj.is_absolute():
            return None
        for segment in path_obj.parts:
            if segment in ("", ".", ".."):
                return None
        # Evita que el primer segmento sea sospechoso (ej. muy largo, control chars)
        safe = path_obj.as_posix().lstrip("/\\")
        return safe or None

    def _handle_empty_file(self, temp_path: str, sha256_hex: str,
                           dest_path: str, file_id: str, src_mac: str,
                           name: str, rel: str | None):
        # started (archivo vacío también cuenta como recepción iniciada)
        self._emit_started(file_id=file_id, src=src_mac, name=name, rel=rel)

        calc = get_file_hash(temp_path)
        if calc.lower() == sha256_hex.lower():
            os.replace(temp_path, dest_path)
            self._send_fin(file_id, src_mac, "ok")
            # Para vacíos: acked=0/total=0 pero progreso 1.0 para forzar "completo"
            self._emit_progress(
                file_id=file_id, src=src_mac, name=name, rel=rel,
                acked=0, total=0, progress=1.0
            )
            self._emit_finished(file_id=file_id, src=src_mac, name=name, rel=rel, status="ok")
        else:
            self._send_fin(file_id, src_mac, "error", "hash_mismatch")
            self._emit_error(file_id=file_id, src=src_mac, name=name, rel=rel, error="hash_mismatch")

        self.ctx_by_id.pop(file_id, None)

    # ---------- Handlers de frames ----------
    def _on_meta(self, frame: FrameSchema):
        kv = parse_payload(frame.payload.decode("utf-8"))

        required = ["file_id", "name", "size", "sha256", "chunk_size", "total"]
        missing = [k for k in required if kv.get(k) is None]
        if missing:
            file_id = kv.get("file_id") or "unknown"
            self._send_fin(file_id, frame.src_mac, "error", "bad_meta_missing")
            self._emit_error(file_id=file_id, src=frame.src_mac, name=None, rel=None, error="bad_meta_missing")
            return

        file_id = kv["file_id"]
        name = kv["name"]
        sha256_hex = kv["sha256"]

        # Soportar ambas claves: 'rel' (preferida) o 'path' (retrocompat).
        rel_raw = kv.get("rel")
        if rel_raw is None:
            rel_raw = kv.get("path")
        rel_path = self._sanitize_relative_path(rel_raw)

        try:
            size = int(kv["size"])
            chunk_size = int(kv["chunk_size"])
            total = int(kv["total"])
        except ValueError:
            self._send_fin(file_id or "unknown", frame.src_mac, "error", "bad_meta_non_numeric")
            self._emit_error(file_id=file_id or "unknown", src=frame.src_mac, name=name, rel=rel_path, error="bad_meta_non_numeric")
            return

        if not file_id or not name or not sha256_hex:
            self._send_fin(file_id or "unknown", frame.src_mac, "error", "bad_meta_empty_str")
            self._emit_error(file_id=file_id or "unknown", src=frame.src_mac, name=name, rel=rel_path, error="bad_meta_empty_str")
            return

        if chunk_size <= 0 or size < 0 or total < 0:
            self._send_fin(file_id, frame.src_mac, "error", "bad_meta_ranges")
            self._emit_error(file_id=file_id, src=frame.src_mac, name=name, rel=rel_path, error="bad_meta_ranges")
            return

        # Construcción de destino: si hay rel, úsalo; si no, sólo el nombre.
        dest_rel = rel_path if rel_path else name
        dest_path = os.path.normpath(os.path.join(self.base_dir, dest_rel))

        # Garantizar que dest_path quede DENTRO de base_dir
        base_real = os.path.realpath(self.base_dir)
        dest_real = os.path.realpath(dest_path)
        if not dest_real.startswith(base_real + os.sep) and dest_real != base_real:
            self._send_fin(file_id, frame.src_mac, "error", "path_outside_base")
            self._emit_error(file_id=file_id, src=frame.src_mac, name=name, rel=rel_path, error="path_outside_base")
            return

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        temp_path = dest_path + ".part"
        # iniciar/limpiar archivo temporal
        with open(temp_path, "wb"):
            pass

        logging.debug(
            "[META<-] file_id=%s name=%s total=%d chunk_size=%d dest=%s",
            file_id, name, total, chunk_size, dest_path
        )

        if total == 0:
            self._handle_empty_file(
                temp_path=temp_path,
                sha256_hex=sha256_hex,
                dest_path=dest_path,
                file_id=file_id,
                src_mac=frame.src_mac,
                name=name,
                rel=dest_rel
            )
            return

        ctx = FileRcvCtxSchema(
            file_id=file_id,
            src_mac=frame.src_mac,
            dst_mac=frame.dst_mac,
            name=name,
            size=size,
            sha256_expected=sha256_hex,
            chunk_size=chunk_size,
            total_chunks=total,
            temp_path=temp_path,
            dest_path=dest_path
        )
        # Guardar también el 'rel' calculado para eventos
        setattr(ctx, "rel", dest_rel)

        self.ctx_by_id[file_id] = ctx

        # Notificamos inicio de recepción (con rel para UI)
        self._emit_started(file_id=file_id, src=frame.src_mac, name=name, rel=dest_rel)

        # Primer ACK
        self._send_ack(file_id, frame.src_mac, next_needed=0)

    def _on_data(self, frame: FrameSchema):
        payload = frame.payload
        sep = payload.find(b"\n\n")  # fin del header (línea en blanco)
        if sep == -1:
            self._send_fin("unknown", frame.src_mac, "error", "bad_payload")
            self._emit_error(file_id="unknown", src=frame.src_mac, name=None, rel=None, error="bad_payload")
            return

        header_bytes = payload[:sep]
        data = payload[sep + 2:]
        s = header_bytes.decode("utf-8")
        kv = parse_payload(s)

        file_id = kv.get("file_id")
        if not file_id or file_id not in self.ctx_by_id:
            return

        ctx = self.ctx_by_id[file_id]
        try:
            idx = int(kv.get("idx", "-1"))
            total = int(kv.get("total", "-1"))
        except ValueError:
            return
        if idx < 0 or idx >= ctx.total_chunks or total <= 0:
            return

        with ctx.lock:
            # escribir chunk
            with open(ctx.temp_path, "r+b") as f:
                f.seek(idx * ctx.chunk_size)
                f.write(data)

            if idx not in ctx.received:
                ctx.received.add(idx)
                # actualizar next_needed (primer índice faltante)
                while ctx.next_needed in ctx.received:
                    ctx.next_needed += 1

            # ACK inmediato
            self._send_ack(ctx.file_id, frame.src_mac, ctx.next_needed)

            # progreso (acked = cantidad recibida efectiva)
            acked = len(ctx.received)
            progress = (acked / ctx.total_chunks) if ctx.total_chunks else 0.0

        # Emitir progreso fuera del lock (usamos el rel guardado en el ctx)
        rel_for_events = getattr(ctx, "rel", os.path.relpath(ctx.dest_path, self.base_dir))
        self._emit_progress(
            file_id=ctx.file_id,
            src=ctx.src_mac,
            name=ctx.name,
            rel=rel_for_events,
            acked=acked,
            total=ctx.total_chunks,
            progress=progress
        )

        # ¿completado?
        finished_now = False
        with ctx.lock:
            if len(ctx.received) >= ctx.total_chunks and not ctx.finished:
                ctx.finished = True
                finished_now = True

        if finished_now:
            calc = get_file_hash(ctx.temp_path)
            if calc.lower() == ctx.sha256_expected.lower():
                os.replace(ctx.temp_path, ctx.dest_path)
                self._send_fin(ctx.file_id, frame.src_mac, "ok")
                self._emit_finished(
                    file_id=ctx.file_id,
                    src=ctx.src_mac,
                    name=ctx.name,
                    rel=rel_for_events,
                    status="ok"
                )
            else:
                self._send_fin(ctx.file_id, frame.src_mac, "error", "hash_mismatch")
                self._emit_error(
                    file_id=ctx.file_id,
                    src=ctx.src_mac,
                    name=ctx.name,
                    rel=rel_for_events,
                    error="hash_mismatch"
                )
            self.ctx_by_id.pop(ctx.file_id, None)
