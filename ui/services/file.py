import asyncio, os, time
from dataclasses import dataclass, field
from typing import Dict

from services.ipc_uds import UDSBridge

@dataclass
class TransferState:
    id: str
    kind: str      # "tx" | "rx"
    name: str
    size: int
    done: int = 0
    status: str = "pending"  # running|done|error|canceled

@dataclass
class FileService:
    bridge: "UDSBridge"
    transfers: Dict[str, TransferState] = field(default_factory=dict)

    def on_file_progress(self, evt: dict):
        tid = evt.get("id")
        if tid in self.transfers:
            self.transfers[tid].done = int(evt.get("bytes", self.transfers[tid].done))

    def on_file_complete(self, evt: dict):
        tid = evt.get("id")
        if tid in self.transfers:
            self.transfers[tid].status = "done" if evt.get("ok") else "error"

    def on_file_offer(self, evt: dict):
        # aquí decidir si autoaceptas o disparas UI de confirmación
        pass

    def send_file(self, dst_mac: str, path: str):
        tid = f"tx-{int(time.time()*1000)}"
        self.transfers[tid] = TransferState(
            id=tid, kind="tx", name=os.path.basename(path), size=os.path.getsize(path)
        )
        loop = asyncio.get_running_loop()
        loop.create_task(self.bridge.send_cmd({"type":"file_send","dst":dst_mac,"path":path}))
