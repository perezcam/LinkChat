


import base64
import binascii
import logging
import os
import pathlib
from typing import Dict
from src.core.enums.enums import MessageType
from src.core.managers.service_threads import ThreadManager
from src.core.schemas.frame_schemas import FrameSchema
from src.file_transfer.helpers.get_file_hash import get_file_hash
from src.file_transfer.helpers.parse_payload import parse_payload
from src.file_transfer.schemas.recv_ctx import FileRcvCtxSchema


class FileReceiver:
    def __init__(self, service_threads: ThreadManager, base_dir: str) -> None:
        self._service_threads = service_threads
        self.ctx_by_id: Dict[str, FileRcvCtxSchema] = {}
        self.base_dir = os.path.abspath(base_dir)

        #Creates directory if not exists
        os.makedirs(self.base_dir, exist_ok=True)

        self._service_threads.add_message_handler(MessageType.FILE_DATA, self._on_data)
        self._service_threads.add_message_handler(MessageType.FILE_META, self._on_meta)

    def _send_ack(self, file_id: str, dst_mac: str, next_needed: int):
        payload = f"file_id={file_id}\nnext_needed={next_needed}\n".encode("utf-8")

        frame = self._service_threads.file_transfer_handler.get_frame(
            dst_mac, MessageType.ACK, payload
        )
        self._service_threads.queue_frame_for_sending(frame)

    def _send_fin(self, file_id: str, dst_mac: str, status: str, reason: str = ""):
        ctx = self.ctx_by_id.get(file_id)
        if not ctx:
            # fallback para empty file (antes de annadirs a ctx by id)
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

    def _sanitize_relative_path(self, raw_path: str) -> str | None:
        """
        Limpia y valida una ruta relativa que viene del emisor.

        Reglas:
        - Rechaza si está vacía.
        - Rechaza si es absoluta (ej. "/etc/passwd" o "C:\\Users\\...").
        - Rechaza si contiene ".." (intento de traversal) o partes vacías.
        - Devuelve la ruta normalizada en formato POSIX (con '/').
        """
        if not raw_path:
            return None

        path_obj = pathlib.PurePosixPath(raw_path)

        if path_obj.is_absolute():
            return None

        for segment in path_obj.parts:
            if segment == ".." or segment == "":
                # ".." sería intento de salir de la carpeta base
                # "" ocurre con dobles barras "//"
                return None

        return path_obj.as_posix()
    
    def _handle_empty_file(self, temp_path: str, sha256_hex: str, dest_path: str, file_id: str, src_mac: str):
        calc = get_file_hash(temp_path)
        if calc.lower() == sha256_hex.lower():
            os.replace(temp_path, dest_path)
            self._send_fin(file_id, src_mac, "ok")
        else:
            self._send_fin(file_id, src_mac, "error", "hash_mismatch")
        if self.ctx_by_id[file_id]: 
            self.ctx_by_id.pop(file_id, None)

    def _on_meta(self, frame: FrameSchema):
        
        kv = parse_payload(frame.payload.decode("utf-8"))

        required = ["file_id", "name", "size", "sha256", "chunk_size", "total"]
        missing = [k for k in required if kv.get(k) is None]  # ojo: None vs ""
        if missing:
            self._send_fin(kv.get("file_id") or "unknown", frame.src_mac, "error", "bad_meta_missing")
            return
        
        file_id = kv["file_id"]
        name = kv["name"]
        sha256_hex = kv["sha256"]
        rel_path = self._sanitize_relative_path(kv.get("path", ""))

        try:
            size = int(kv["size"])
            chunk_size = int(kv["chunk_size"])
            total = int(kv["total"])
        except ValueError:
            self._send_fin(file_id or "unknown", frame.src_mac, "error", "bad_meta_non_numeric")
            return

        if not file_id or not name or not sha256_hex:
            self._send_fin(file_id or "unknown", frame.src_mac, "error", "bad_meta_empty_str")
            return
        
        if chunk_size <= 0 or size < 0 or total < 0:
            self._send_fin(file_id, frame.src_mac, "error", "bad_meta_ranges")
            return
                
       
        dest_rel = rel_path if rel_path else name
        dest_path = os.path.normpath(os.path.join(self.base_dir, dest_rel))
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        temp_path = dest_path + ".part"
        open(temp_path, "wb").close()

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
                src_mac=frame.src_mac
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
        self.ctx_by_id[file_id] = ctx

        self._send_ack(file_id, frame.src_mac, next_needed=0)

    def _on_data(self, frame: FrameSchema):

        payload = frame.payload
        sep = payload.find(b"\n\n")  # fin del header (línea en blanco)
        if sep == -1:
            self._send_fin("unknown", frame.src_mac, "error", "bad_payload")
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
            idx   = int(kv.get("idx", "-1"))
            total = int(kv.get("total", "-1"))
        except ValueError:
            return
        if idx < 0 or idx >= ctx.total_chunks or total <= 0:
            return

        with ctx.lock:
            #escribir en offset
            with open(ctx.temp_path, "r+b") as f:
                f.seek(idx * ctx.chunk_size)
                f.write(data)

            if idx not in ctx.received:
                ctx.received.add(idx)
                # actualizar next_needed (primer índice faltante)
                while ctx.next_needed in ctx.received:
                    ctx.next_needed += 1
            
            self._send_ack(ctx.file_id, frame.src_mac, ctx.next_needed)

            # ¿completado?
            if len(ctx.received) >= ctx.total_chunks and not ctx.finished:
                ctx.finished = True

        # Valida hash fuera de el lock
        if ctx.finished:
            calc = get_file_hash(ctx.temp_path)  
            if calc.lower() == ctx.sha256_expected.lower():
                # Mueve .part -> destino final
                os.replace(ctx.temp_path, ctx.dest_path)
                self._send_fin(ctx.file_id, frame.src_mac, "ok")
                self.ctx_by_id.pop(ctx.file_id, None)
            else:
                self._send_fin(ctx.file_id, frame.src_mac, "error", "hash_mismatch")
                self.ctx_by_id.pop(ctx.file_id, None)

