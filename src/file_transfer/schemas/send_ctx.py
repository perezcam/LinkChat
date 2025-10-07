from dataclasses import dataclass, field
import threading
from typing import Dict, Set, Tuple

@dataclass
class FileSendCtxSchema:
    file_id: str
    dst_mac: str
    path: str
    size: int
    hash_sha256_hex: str
    chunk_size: int
    total_chunks: int

    # send control
    window_size: int = 16  
    timeout_s: float = 0.6
    max_retries: int = 10
    next_to_send: int = 0
    last_acked: int = -1
    inflight: Dict[int, Tuple[float, int]] = field(default_factory=dict)
    acked: Set[int] = field(default_factory=set)
    finished: bool = False
    meta_acked: bool = False
    meta_sent_ts: float = 0.0

    lock: threading.Lock = field(default_factory=threading.Lock, repr=False) #mutex



    def debug_snapshot(self) -> str:
        inflight = sorted(self.inflight.keys())
        return (
            f"[SENDCTX id={self.file_id}] "
            f"next_to_send={self.next_to_send} "
            f"last_acked={self.last_acked} "
            f"inflight={inflight} "
            f"acked_count={len(self.acked)}/{self.total_chunks} "
            f"win={self.window_size} "
            f"timeout={self.timeout_s}s "
            f"retries={[self.inflight[i][1] for i in inflight]}"
    )
