import os
import asyncio
import logging

from services.ipc_uds import UDSBridge
from services.eventPump import EventPump
from services.roster import RosterService
from services.chat import ChatService
from services.file import FileService
from app import run


async def main():
    # --- Logging ---
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - [UI] %(message)s",
        force=True,
    )

    sock = os.environ.get("IPC_SOCKET", "/ipc/linkchat-Nodo-A.sock")
    logging.info("Iniciando UI (IPC_SOCKET=%s)", sock)

    # --- IPC Bridge ---
    bridge = UDSBridge(sock)
    logging.info("[IPC] Conectando a %s ...", sock)
    await bridge.start()
    logging.info("[IPC] Conexión establecida y readerLoop en marcha.")

    # --- Servicios de la UI ---
    roster = RosterService(bridge)
    chat   = ChatService(bridge)
    files  = FileService(bridge) 

    # --- Event Pump y suscripciones ---
    pump = EventPump()
    pump.subscribe("neighbors_changed", roster.on_neighbors_changed)
    pump.subscribe("chat",               chat.on_chat)

    # Fallback (opcional): ignora respuestas sin "type" (p.ej. {"ok": true})
    pump.fallback(lambda ev: None if (isinstance(ev, dict) and "type" not in ev)
                  else logging.info("[UI] evento no manejado: %s", ev))

    # --- Bootstrap de estado inicial ---
    await roster.bootstrap()
    logging.info("[UI] Bootstrap enviado (neighbors_get).")

    # Ping opcional
    await bridge.send_cmd({"type": "ping"})

    # --- Arrancar la app principal (Pygame corre en otro hilo) ---
    await asyncio.to_thread(run, bridge, pump, roster, chat, files)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.exception("Fallo inesperado en la UI")
