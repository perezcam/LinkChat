from dataclasses import dataclass, field
import os
from src.core.enums.enums import MessageType
from src.core.managers.service_threads import ThreadManager
from src.core.schemas.frame_schemas import FrameSchema
from src.file_transfer.helpers.parse_payload import parse_payload
from src.file_transfer.helpers.get_file_hash import get_file_hash
from src.file_transfer.schemas.send_ctx import FileCtxSchema


class FileSender: 
    def __init__(self, service_threads: ThreadManager, chunk_size: int):
        self.service_threads = service_threads
        self._chunk_size = chunk_size

        self.service_threads.add_message_handler(MessageType.ACK, self._on_ack) 
        self.service_threads.add_message_handler(MessageType.FILE_FIN, self._on_fin)

    def send_file(self, path: str, dst_mac: str):

        if not os.path.isfile(path):
            print("No se encontró ningún archivo en ", path)
            raise FileNotFoundError(path)
        
        file_size = os.path.getsize(path)
        hash_sha256_hex = get_file_hash(path)
        file_name = os.path.basename(path)

        total_chunks = (file_size + self._chunk_size -1) // self._chunk_size
        file_id = f"{file_name}-{hash_sha256_hex[:12]}"

        ctx = FileCtxSchema(
            file_id=file_id,
            dst_mac=dst_mac,
            path=path,
            size=file_size,
            hash_sha256_hex=hash_sha256_hex,
            chunk_size=self._chunk_size,
            total_chunks=total_chunks
        )
        self.service_threads.add_ctx_by_id(file_id, ctx)

        #Enviar META inicial
        self._send_meta(ctx, file_name)
        return file_id
    

    def _send_meta(self, ctx: FileCtxSchema, file_name: str):
        payload = (
            f"file_id={ctx.file_id}\n"
            f"name={file_name}\n"
            f"size={ctx.size}\n"
            f"sha256={ctx.hash_sha256_hex}\n"
            f"chunk_size={ctx.chunk_size}\n"
            f"total={ctx.total_chunks}\n"
        )
        frame: FrameSchema = self.service_threads.file_transfer_handler.get_frame(ctx.dst_mac, MessageType.FILE_META, payload.encode("utf-8"))
        self.service_threads.queue_frame_for_sending(frame)


    def _on_ack(self, frame: FrameSchema):
        payload = frame.payload.decode("utf-8")
        kv = parse_payload(payload)
        file_id = kv.get("file_id")
        if not file_id:
            return
        ctx = self.service_threads.get_ctx_by_id(file_id)
        if not ctx or ctx.finished:
            return
        try:
            next_needed = int(kv.get("next_needed", "0"))
        except ValueError:
            return
        # Marca como ACK todo < next_needed
        for idx in list(ctx.inflight.keys()):
            if idx < next_needed:
                ctx.acked.add(idx)
                ctx.inflight.pop(idx, None)
                ctx.last_acked = max(ctx.last_acked, next_needed - 1)

    def _on_fin(self, frame: FrameSchema):
        payload = frame.payload.decode("utf-8")
        kv = parse_payload(payload)

        file_id = kv.get("file_id")
        status = kv.get("status")

        if not file_id:
            return
        ctx = self.service_threads.get_ctx_by_id(file_id)

        if not ctx:
            return
        
        ctx.finished = True
        if status != "ok":
            reason = kv.get("reason", "")
            print(f"FIN error para {file_id}: {reason}")
