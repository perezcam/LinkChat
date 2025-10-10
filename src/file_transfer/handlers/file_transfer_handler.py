import base64

from src.prepare.network_config import get_ether_type
from src.core.enums.enums import MessageType
from src.core.schemas.frame_schemas import FrameSchema, HeaderSchema
from src.file_transfer.schemas.send_ctx import FileSendCtxSchema


class FileTransferHandler:
    def __init__(self, src_mac: str) -> None:
        self._seq = 0
        self._src_mac = src_mac 

    def _kv_bytes(self, **kwargs):
        # Serializa en líneas: key=value\n
        return ("\n".join(f"{k}={v}" for k, v in kwargs.items()) + "\n").encode("utf-8")

    def get_file_fin_frame(self, ctx: FileSendCtxSchema, status: str, reason: str = "") -> FrameSchema:
        payload_bytes = self._kv_bytes(file_id=ctx.file_id, status=status) if not reason \
                        else self._kv_bytes(file_id=ctx.file_id, status=status, reason=reason)
        return self.get_frame(ctx.dst_mac, MessageType.FILE_FIN, payload_bytes)
    
    def receiver_get_file_fin_frame(self, dst_mac: str, file_id: str, status: str, reason: str = "") -> FrameSchema:
        payload_bytes = self._kv_bytes(file_id=file_id, status=status) if not reason \
                        else self._kv_bytes(file_id=file_id, status=status, reason=reason)
        return self.get_frame(dst_mac, MessageType.FILE_FIN, payload_bytes)
    

    def get_data_chunk(self, ctx: FileSendCtxSchema, idx: int) -> FrameSchema:
        #Get chunk of file 
        with open(ctx.path, "rb") as f:
            f.seek(idx * ctx.chunk_size)
            data = f.read(ctx.chunk_size)
        #Convert it to string
        b64 = base64.b64encode(data).decode("ascii") 
        payload = self._kv_bytes(
            file_id=ctx.file_id,
            idx=idx,
            total=ctx.total_chunks,
            data_b64=b64
        )
        return self.get_frame(ctx.dst_mac, MessageType.FILE_DATA, payload)
        
    def get_frame(self, dst_mac: str, msg_type: MessageType, payload: bytes) -> FrameSchema:
        self._seq = (self._seq + 1) & 0xFFFF

        return FrameSchema(
            dst_mac=dst_mac,
            src_mac=self._src_mac, 
            ethertype=get_ether_type(),
            header=HeaderSchema(
                message_type=msg_type,
                payload_len=len(payload),
                sequence=self._seq 
            ),
            payload=payload
        )
    
    def get_meta_frame(self, ctx: FileSendCtxSchema, file_name: str, rel_path: str | None = None) -> FrameSchema:
        kv = dict(
            file_id=ctx.file_id,
            name=file_name,
            size=ctx.size,
            sha256=ctx.hash_sha256_hex,
            chunk_size=ctx.chunk_size,
            total=ctx.total_chunks
        )
        if rel_path:
            kv["path"] = rel_path
        payload = self._kv_bytes(**kv)
        return self.get_frame(ctx.dst_mac, MessageType.FILE_META, payload)
    
