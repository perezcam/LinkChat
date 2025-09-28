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
    received: Set[int] = field(default_factory=set)
    next_needed: int = 0
    finished: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


    #TODO: borrar esto despues!, definir el path 
    @staticmethod
    def make_temp_path(file_id: str) -> str:
        # un nombre simple predecible; puedes usar tempfile.NamedTemporaryFile si prefieres aleatorio
        base = tempfile.gettempdir()
        return os.path.join(base, f"{file_id}.part")
