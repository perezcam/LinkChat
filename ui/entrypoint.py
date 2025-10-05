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
    print("saliendo de start")
    logging.info("[IPC] Conexión establecida y readerLoop en marcha.")

    # --- Servicios de la UI ---
    roster = RosterService(bridge)
    chat   = ChatService(bridge)
    files  = FileService(bridge)

    # --- Event Pump y suscripciones ---
    pump = EventPump()
    pump.subscribe("neighbors_changed", roster.on_neighbors_changed)
    pump.subscribe("chat",               chat.on_chat)
    pump.subscribe("file_progress",      files.on_file_progress)
    pump.subscribe("file_complete",      files.on_file_complete)
    pump.subscribe("file_offer",         files.on_file_offer)

    # Fallback para ver TODO lo que llega aunque no tenga handler
    pump.fallback(lambda evt: logging.info("[UI] evento no manejado: %s", evt))

    # --- Bootstrap de estado inicial (pide vecinos) ---
    await roster.bootstrap()
    logging.info("[UI] Bootstrap enviado (neighbors_get).")

    # Ping opcional para comprobar ida/vuelta (aparecerá como evento)
    await bridge.send_cmd({"type": "ping"})

    # --- Arrancar la app principal (main loop hace pump de eventos) ---
    await asyncio.to_thread(run, bridge, pump, roster, chat, files)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.exception("Fallo inesperado en la UI")
