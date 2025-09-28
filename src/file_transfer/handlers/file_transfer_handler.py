import base64
from network_config import get_ether_type
from src.core.enums.enums import MessageType
from src.core.schemas.frame_schemas import FrameSchema, HeaderSchema
from src.file_transfer.schemas.send_ctx import FileCtxSchema


class FileTransferHandler:
    def __init__(self) -> None:
        self._seq = 0
        self._src_mac = get_src_mac() #TODO: ADD src mac in config 

    def _kv_bytes(self, **kwargs):
        # Serializa en líneas: key=value\n
        return ("\n".join(f"{k}={v}" for k, v in kwargs.items()) + "\n").encode("utf-8")

    def get_file_fin_frame(self, ctx: FileCtxSchema, status: str, reason: str = "") -> FrameSchema:
        payload_bytes = self._kv_bytes(file_id=ctx.file_id, status=status) if not reason \
                        else self._kv_bytes(file_id=ctx.file_id, status=status, reason=reason)
        return self.get_frame(ctx.dst_mac, MessageType.FILE_FIN, payload_bytes)
    

    def get_data_chunk(self, ctx: FileCtxSchema, idx: int) -> FrameSchema:
        #Get chunk of file 
        with open(ctx.path, "rb") as f:
            f.seek(idx * ctx.chunk_size)
            data = f.read(ctx.chunk_size)
        #Convert it to string
        b64 = base64.b64encode(data).decode("ascii")
        payload = self._kv_bytes(
            file_id={ctx.file_id},
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
                sequence=self._seq #TODO: Preguntarle a Camilo como annadir el checksum? Se agrega en create_etehrnet_frame?
            ),
            payload=payload
        )
    
