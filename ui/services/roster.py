from dataclasses import dataclass, field
from typing import List, Dict, Optional
from state.models import Contact
from services.ipc_uds import UDSBridge

@dataclass
class RosterService:
    bridge: "UDSBridge"
    contacts: List[Contact] = field(default_factory=list)
    selected_mac: Optional[str] = None
    _idx: Dict[str,int] = field(default_factory=dict)

    async def bootstrap(self):
        await self.bridge.send_cmd({"type":"neighbors_get"})

    # === Handlers que registra el EventPump ===
    def on_neighbors_changed(self, evt: dict):
        rows = evt.get("rows", [])
        for r in rows:
            print('El tipo de r es:',r)
            mac = r.get("mac"); alias = r.get("alias") or "?"
            online = (r.get("last_seen_ms", 1e9) < 10_000)
            if mac in self._idx:
                i = self._idx[mac]
                c = self.contacts[i]
                c.name = alias; c.online = online
            else:
                self._idx[mac] = len(self.contacts)
                self.contacts.append(Contact(mac=mac, name=alias, online=online))
        self.contacts.sort(key=lambda c: (not c.online, c.name.lower()))
        if not self.selected_mac and self.contacts:
            self.selected_mac = self.contacts[0].mac

    def select(self, mac: str):
        if mac in self._idx:
            self.selected_mac = mac
