import logging
import os
import pathlib
from typing import Dict, Any

from src.core.enums.enums import MessageType
from src.core.managers.service_threads import ThreadManager
from src.core.schemas.frame_schemas import FrameSchema
from src.file_transfer.helpers.get_file_hash import get_file_hash
from src.file_transfer.helpers.parse_payload import parse_payload
from src.file_transfer.schemas.recv_ctx import FileRcvCtxSchema

from src.file_transfer.handlers.ui_events import (
    emit_started, emit_progress, emit_finished, emit_error
)


class FileReceiver:
    def __init__(self, service_threads: ThreadManager, base_dir: str) -> None:
        self._service_threads = service_threads
        self.ctx_by_id: Dict[str, FileRcvCtxSchema] = {}
        self.base_dir = os.path.abspath(base_dir)

        os.makedirs(self.base_dir, exist_ok=True)
        self._service_threads.add_message_handler(MessageType.FILE_DATA, self._on_data)
        self._service_threads.add_message_handler(MessageType.FILE_META, self._on_meta)


    def _send_ack(self, file_id: str, dst_mac: str, next_needed: int):
        payload = f"file_id={file_id}\nnext_needed={next_needed}\n".encode("utf-8")
        frame = self._service_threads.file_transfer_handler.get_frame(dst_mac, MessageType.ACK, payload)
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
                dst_mac=dst_mac, file_id=file_id, status=status, reason=reason
            )
        self._service_threads.queue_frame_for_sending(frame)

    # helpers de path
    def _sanitize_relative_path(self, raw_path: str | None) -> str | None:
        """Valida una ruta relativa POSIX (no absoluta, sin '..', sin partes vacías)."""
        if not raw_path:
            return None
        p = pathlib.PurePosixPath(raw_path)
        if p.is_absolute():
            return None
        for seg in p.parts:
            if seg in ("", ".."):
                return None
        return p.as_posix()

    def _to_posix_relative(self, full_path: str, base_dir_for_rel: str) -> str | None:
        """
        Convierte un path absoluto/normalizado a relativo POSIX respecto a base_dir_for_rel.
        Devuelve None si no puede relativizar o si escapa del base.
        """
        try:
            full_real = os.path.realpath(os.path.normpath(full_path))
            base_real = os.path.realpath(os.path.normpath(base_dir_for_rel))
            if not (full_real == base_real or full_real.startswith(base_real + os.sep)):
                return None
            rel = os.path.relpath(full_real, base_real)
            return self._sanitize_relative_path(pathlib.PurePath(rel).as_posix())
        except Exception:
            return None

    def _ensure_inside_base_dir(self, candidate_path: str) -> bool:
        """Asegura que candidate_path quede dentro de self.base_dir."""
        base_real = os.path.realpath(self.base_dir)
        cand_real = os.path.realpath(candidate_path)
        return cand_real == base_real or cand_real.startswith(base_real + os.sep)

    # Meta
    def _on_meta(self, frame: FrameSchema):
        kv: Dict[str, Any] = parse_payload(frame.payload.decode("utf-8"))
        required = ["file_id", "name", "size", "sha256", "chunk_size", "total"]
        missing = [k for k in required if kv.get(k) is None]
        if missing:
            file_id = kv.get("file_id") or "unknown"
            self._send_fin(file_id, frame.src_mac, "error", "bad_meta_missing")
            emit_error(file_id=file_id, src=frame.src_mac, name=None, rel=None, error="bad_meta_missing")
            return

        file_id = kv["file_id"]
        name = kv["name"]
        sha256_hex = kv["sha256"]

        rel_path = None
        for cand in (kv.get("path"), kv.get("rel")):
            rel_path = self._sanitize_relative_path(cand)
            if rel_path:
                break


        # Validaciones numericas
        try:
            size = int(kv["size"])
            chunk_size = int(kv["chunk_size"])
            total = int(kv["total"])
        except ValueError:
            self._send_fin(file_id or "unknown", frame.src_mac, "error", "bad_meta_non_numeric")
            emit_error(file_id=file_id or "unknown", src=frame.src_mac, name=name, rel=rel_path, error="bad_meta_non_numeric")
            return

        if not file_id or not name or not sha256_hex:
            self._send_fin(file_id or "unknown", frame.src_mac, "error", "bad_meta_empty_str")
            emit_error(file_id=file_id or "unknown", src=frame.src_mac, name=name, rel=rel_path, error="bad_meta_empty_str")
            return

        if chunk_size <= 0 or size < 0 or total < 0:
            self._send_fin(file_id, frame.src_mac, "error", "bad_meta_ranges")
            emit_error(file_id=file_id, src=frame.src_mac, name=name, rel=rel_path, error="bad_meta_ranges")
            return

        # Destino final
        dest_rel = rel_path if rel_path else name
        dest_path = os.path.normpath(os.path.join(self.base_dir, dest_rel))

        if not self._ensure_inside_base_dir(dest_path):
            self._send_fin(file_id, frame.src_mac, "error", "path_outside_base")
            emit_error(file_id=file_id, src=frame.src_mac, name=name, rel=rel_path, error="path_outside_base")
            return

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        temp_path = dest_path + ".part"
        open(temp_path, "wb").close()

        logging.debug(
            "[META<-] file_id=%s name=%s total=%d chunk_size=%d dest=%s",
            file_id, name, total, chunk_size, dest_path
        )

        emit_started(file_id=file_id, src=frame.src_mac, name=name, rel=dest_rel)

        # Archivo vacio
        if total == 0:
            calc = get_file_hash(temp_path)
            if calc.lower() == sha256_hex.lower():
                os.replace(temp_path, dest_path)
                self._send_fin(file_id, frame.src_mac, "ok")
                emit_progress(
                    file_id=file_id, src=frame.src_mac, name=name, rel=dest_rel,
                    acked=0, total=0, progress=1.0
                )
                emit_finished(file_id=file_id, src=frame.src_mac, name=name, rel=dest_rel, status="ok")
            else:
                self._send_fin(file_id, frame.src_mac, "error", "hash_mismatch")
                emit_error(file_id=file_id, src=frame.src_mac, name=name, rel=dest_rel, error="hash_mismatch")
            self.ctx_by_id.pop(file_id, None)
            return

        # contexto
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
        setattr(ctx, "rel", dest_rel)
        self.ctx_by_id[file_id] = ctx

        self._send_ack(file_id, frame.src_mac, next_needed=0)

    # Data
    def _on_data(self, frame: FrameSchema):
        payload = frame.payload
        sep = payload.find(b"\n\n")
        if sep == -1:
            self._send_fin("unknown", frame.src_mac, "error", "bad_payload")
            emit_error(file_id="unknown", src=frame.src_mac, name=None, rel=None, error="bad_payload")
            return

        header_bytes = payload[:sep]
        data = payload[sep + 2:]
        kv = parse_payload(header_bytes.decode("utf-8"))

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
            with open(ctx.temp_path, "r+b") as f:
                f.seek(idx * ctx.chunk_size)
                f.write(data)

            if idx not in ctx.received:
                ctx.received.add(idx)
                while ctx.next_needed in ctx.received:
                    ctx.next_needed += 1

            self._send_ack(ctx.file_id, frame.src_mac, ctx.next_needed)
            acked = len(ctx.received)
            progress = (acked / ctx.total_chunks) if ctx.total_chunks else 0.0

        rel_for_events = getattr(ctx, "rel", os.path.basename(ctx.dest_path))
        emit_progress(
            file_id=ctx.file_id,
            src=ctx.src_mac,
            name=ctx.name,
            rel=rel_for_events,
            acked=acked,
            total=ctx.total_chunks,
            progress=progress
        )

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
                emit_finished(
                    file_id=ctx.file_id,
                    src=ctx.src_mac,
                    name=ctx.name,
                    rel=rel_for_events,
                    status="ok"
                )
            else:
                self._send_fin(ctx.file_id, frame.src_mac, "error", "hash_mismatch")
                emit_error(
                    file_id=ctx.file_id,
                    src=ctx.src_mac,
                    name=ctx.name,
                    rel=rel_for_events,
                    error="hash_mismatch"
                )
            self.ctx_by_id.pop(ctx.file_id, None)
