from typing import Callable, Dict, List, Any, Optional

from services.ipc_uds import UDSBridge

Handler = Callable[[dict], None]

class EventPump:
    """
    Extrae eventos crudos del UDSBridge y los reparte a servicios
    suscritos por 'type'
    - subscribe("chat", handler)             # 1..N handlers por tipo
    - subscribe_many({"chat":h1, "neighbors_changed":h2})
    - pump(bridge, max_events=100)           # drena hasta N eventos pendientes
    - fallback(handler)                      # para eventos sin handler
    """
    def __init__(self):
        self._subs: Dict[str, List[Handler]] = {}
        self._fallback: Optional[Handler] = None

    def subscribe(self, ev_type: str, handler: Handler):
        ev_type = (ev_type or "").lower()
        self._subs.setdefault(ev_type, []).append(handler)

    def subscribe_many(self, mapping: Dict[str, Handler]):
        for t, h in mapping.items():
            self.subscribe(t, h)

    def fallback(self, handler: Handler):
        self._fallback = handler

    def pump(self, bridge:UDSBridge, max_events: int = 200):
        # Drena hasta max_events de bridge.poll_event()
        # y los reparte. No bloquea.

        for _ in range(max_events):
            evt = bridge.poll_event()
            if not evt:
                break
            print("evento analizando", evt);
            t = (evt.get("type") or "").lower()
            handlers = self._subs.get(t)
            if handlers:
                for h in handlers:
                    try:
                        h(evt)
                    except Exception:
                        # evita que un servicio caído trabaje el resto
                        import logging; logging.exception("Handler error for %s", t)
            elif self._fallback:
                try:
                    self._fallback(evt)
                except Exception:
                    import logging; logging.exception("Fallback handler error")
