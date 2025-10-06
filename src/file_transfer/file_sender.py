from dataclasses import dataclass, field
import logging
import os
import pathlib
import time
from src.core.enums.enums import MessageType
from src.core.managers.service_threads import ThreadManager
from src.core.schemas.frame_schemas import FrameSchema
from src.file_transfer.helpers.parse_payload import parse_payload
from src.file_transfer.helpers.get_file_hash import get_file_hash
from src.file_transfer.schemas.send_ctx import FileSendCtxSchema


class FileSender: 
    def __init__(self, service_threads: ThreadManager, chunk_size: int):
        self.service_threads = service_threads
        self._chunk_size = chunk_size

        self.service_threads.add_message_handler(MessageType.ACK, self._on_ack) 
        self.service_threads.add_message_handler(MessageType.FILE_FIN, self._on_fin)

    def _to_posix_relative(self, path: str, root: str) -> str:
        rel = os.path.relpath(path, root)
        return pathlib.PurePosixPath(rel).as_posix()

    def send_folder(self, folder_path: str, dst_mac: str):
        folder_path = os.path.abspath(folder_path)
        sent = []
        for root, _, files in os.walk(folder_path):
            for fname in files: 
                full_path = os.path.join(root, fname)
                rel_path = self._to_posix_relative(full_path, folder_path)
                file_id = self.send_file(full_path, dst_mac, rel_path)

                ctx = self.service_threads.get_ctx_by_id(file_id)
                while ctx and not ctx.finished:
                    time.sleep(0.05)

                sent.append((file_id, rel_path))
        return sent



    def send_file(self, path: str, dst_mac: str, rel_path: str | None = None):

        if not os.path.isfile(path):
            print("No se encontró ningún archivo en ", path)
            raise FileNotFoundError(path)
        
        file_size = os.path.getsize(path)
        hash_sha256_hex = get_file_hash(path)
        file_name = os.path.basename(path)

        total_chunks = (file_size + self._chunk_size -1) // self._chunk_size
        file_id = f"{file_name}-{hash_sha256_hex[:12]}"

        ctx = FileSendCtxSchema(
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
        self._send_meta(ctx, file_name, rel_path=rel_path)
        # Esperar ACK inicial (gating) para evitar DATA antes que META
        start_wait = time.time()
        while not ctx.meta_acked and not ctx.finished:
            time.sleep(0.02)
            # Reintentar META si nadie responde por 1.5 s
            if ctx.meta_sent_ts > 0 and (time.time() - ctx.meta_sent_ts) >= 1.5:
                self._send_meta(ctx, file_name, rel_path=rel_path)
            if time.time() - start_wait > 30:
                frame = self.service_threads.file_transfer_handler.get_file_fin_frame(ctx, "error", "meta_timeout")
                self.service_threads.queue_frame_for_sending(frame)
                with ctx.lock:
                    ctx.finished = True
                break

        return file_id
    

    def _send_meta(self, ctx: FileSendCtxSchema, file_name: str, rel_path: str | None = None):
        frame: FrameSchema = self.service_threads.file_transfer_handler.get_meta_frame(
            ctx=ctx,
            file_name=file_name,
            rel_path=rel_path
        )
        self.service_threads.queue_frame_for_sending(frame)
        logging.debug(
            "[META->] file_id=%s name=%s size=%d chunks=%d chunk_size=%d sha256=%s",
            ctx.file_id, file_name, ctx.size, ctx.total_chunks, ctx.chunk_size, ctx.hash_sha256_hex[:12]
        )
        ctx.meta_sent_ts = time.time()


    def _on_ack(self, frame: FrameSchema):
        payload = frame.payload.decode("utf-8")
        kv = parse_payload(payload)



        file_id = kv.get("file_id")

        logging.debug("[ACK<-] file_id=%s next_needed=%s", file_id, kv.get("next_needed"))
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
        with ctx.lock:
            if not ctx.meta_acked and next_needed == 0:
                ctx.meta_acked = True
            for idx in list(ctx.inflight.keys()):
                if idx < next_needed:
                    ctx.acked.add(idx)
                    ctx.inflight.pop(idx, None)
            ctx.last_acked = max(ctx.last_acked, next_needed - 1)

            logging.debug("[ACK<-] updated %s", ctx.debug_snapshot())

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
        logging.debug("[ACK<-] updated %s", ctx.debug_snapshot())
        
        with ctx.lock:
            ctx.finished = True
        if status != "ok":
            reason = kv.get("reason", "")
            print(f"FIN error para {file_id}: {reason}")
