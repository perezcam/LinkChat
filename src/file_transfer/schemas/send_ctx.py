from dataclasses import dataclass, field
import threading
from typing import Dict, Set, Tuple

@dataclass
class FileCtxSchema:
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

    lock: threading.Lock = field(default_factory=threading.Lock, repr=False) #mutex
