


import base64
import os
from typing import Dict
from src.core.enums.enums import MessageType
from src.core.managers.service_threads import ThreadManager
from src.core.schemas.frame_schemas import FrameSchema
from src.file_transfer.helpers.get_file_hash import get_file_hash
from src.file_transfer.helpers.parse_payload import parse_payload
from src.file_transfer.schemas.recv_ctx import FileRcvCtxSchema


class FileReceiver:
    def __init__(self, service_threads: ThreadManager) -> None:
        self._service_threads = service_threads
        self.ctx_by_id: Dict[str, FileRcvCtxSchema] = {}

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
            # fallback si no hubiera ctx (raro)
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

    def _on_meta(self, frame: FrameSchema):
        kv = parse_payload(frame.payload.decode("utf-8"))
        file_id = kv.get("file_id")
        name = kv.get("name")
        size = int(kv.get("size", "0"))
        sha256_hex = kv.get("sha256", "")
        chunk_size = int(kv.get("chunk_size", "0"))
        total = int(kv.get("total", "0"))

        if not file_id or not name or not size or not chunk_size or not total:
            # Meta incompleta: responde error temprano
            self._send_fin(file_id or "unknown", frame.src_mac, "error", "bad_meta")
            return
        
        temp_path = FileRcvCtxSchema.make_temp_path(file_id)
        # Pre-crear archivo con tamaño final (opcional), o simplemente crear/cortar a demanda.
        # Aquí creamos vacío; usaremos seek/write por chunk.
        open(temp_path, "wb").close()

        ctx = FileRcvCtxSchema(
            file_id=file_id,
            src_mac=frame.src_mac,
            dst_mac=frame.dst_mac,
            name=name,
            size=size,
            sha256_expected=sha256_hex,
            chunk_size=chunk_size,
            total_chunks=total,
            temp_path=temp_path
        )
        self.ctx_by_id[file_id] = ctx

        self._send_ack(file_id, frame.src_mac, next_needed=0)

    def _on_data(self, frame: FrameSchema):
        s = frame.payload.decode("utf-8")

        #  Asegúrate de que el emisor ponga '\n'.
        kv = parse_payload(s)
        file_id = kv.get("file_id")
        if not file_id or file_id not in self.ctx_by_id:
            return 
        
        ctx = self.ctx_by_id[file_id]
        try: 
            idx   = int(kv.get("idx", "-1"))
            total = int(kv.get("total", "-1"))
            b64   = kv.get("data_b64", "")
        except ValueError:
            return
        if idx < 0 or total <= 0 or not b64:
            return
        
        # coherencia con META
        if total != ctx.total_chunks:
            # TODO: ignora/avisa: total cambió
            pass

        data = base64.b64decode(b64.encode("ascii"))

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

        # Si se completó, valida hash fuera del lock (evita bloquear)
        if ctx.finished:
            calc = get_file_hash(ctx.temp_path)  
            if calc.lower() == ctx.sha256_expected.lower():
                self._send_fin(ctx.file_id, frame.src_mac, "ok")
            else:
                self._send_fin(ctx.file_id, frame.src_mac, "error", "hash_mismatch")
