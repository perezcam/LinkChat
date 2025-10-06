from dataclasses import dataclass, field
from typing import Set
import threading, os, tempfile

@dataclass
class FileRcvCtxSchema:
    file_id: str
    src_mac: str                 # MAC del emisor
    dst_mac: str                    #MAC de el receptor
    name: str
    size: int
    sha256_expected: str
    chunk_size: int
    total_chunks: int
    temp_path: str               # ruta al archivo temporal
    dest_path: str
    received: Set[int] = field(default_factory=set)
    next_needed: int = 0
    finished: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)



def debug_snapshot(self) -> str:
    rcvd = len(self.received)
    first_missing = self.next_needed
    return (
        f"[RECVCTX id={self.file_id}] "
        f"next_needed={self.next_needed} "
        f"received={rcvd}/{self.total_chunks} "
        f"finished={self.finished} "
        f"dest='{self.dest_path}' "
    )