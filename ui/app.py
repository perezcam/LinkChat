import pygame as pg
import pygame_gui
from datetime import datetime
from typing import List, Dict

from services.ipc_uds import UDSBridge
from services.eventPump import EventPump
from services.roster import RosterService
from services.chat import ChatService
from services.file import FileService

from core.theme import CLR
from core.layout import init_window, compute_layout
from components.sidebar import Sidebar
from components.header import ChatHeader
from components.messages import MessagesView
from components.input_bar import InputBar
from components.attachment_picker import AttachmentPicker
from state.models import ChatMessage, Contact


def _build_sidebar_rows(contacts: List[Contact], chat_messages: Dict[str, List[ChatMessage]]):
    """Prepara los datos para pintar la lista del sidebar (último mensaje y hora)."""
    rows = []
    for c in contacts:
        last = chat_messages.get(c.mac, [])
        last_text = last[-1].text if last else ""
        last_time = last[-1].time if last else ""
        rows.append({
            "mac": c.mac,
            "name": c.name,
            "online": c.online,
            "last_msg": last_text,
            "last_time": last_time,
        })
    return rows


def run(
    bridge: UDSBridge,
    pump: EventPump,
    roster: RosterService,
    chat: ChatService,
    files: FileService,
):
    """
    Orquestador gráfico:
      - Procesa input de usuario.
      - Drena eventos con EventPump (neighbors_changed, chat, file_*).
      - Dibuja usando el estado de los servicios (roster, chat, files).
    """
    pg.init()
    screen = init_window()
    clock = pg.time.Clock()

    manager = pygame_gui.UIManager(screen.get_size())
    picker = AttachmentPicker(manager)

    # --- suscribir FileService a eventos de transferencia ---
    if hasattr(files, "register_event_handlers"):
        files.register_event_handlers(pump)

    # --- (opcional) ignorar eventos sin "type" ---
    if hasattr(pump, "fallback"):
        pump.fallback(lambda ev: None if (isinstance(ev, dict) and "type" not in ev) else print("[UI] evento no manejado:", ev))

    sidebar = Sidebar()
    header = ChatHeader()
    messages = MessagesView()
    inputbar = InputBar()

    running = True
    while running:
        dt = clock.tick(60)
        time_delta = dt / 1000.0

        # ----------------- INPUT -----------------
        for e in pg.event.get():
            if e.type == pg.QUIT:
                running = False
                break
            elif e.type == pg.KEYDOWN and e.key == pg.K_q and (pg.key.get_mods() & pg.KMOD_CTRL):
                running = False
                break
            else:
                manager.process_events(e)
                picker.process_event(e)

                #sidebar selección de contacto
                try:
                    w, h = screen.get_size()
                    L = compute_layout(w, h)
                    maybe_mac = sidebar.handle_event(e, L, roster.contacts)
                    if maybe_mac:
                        roster.select(maybe_mac)
                except TypeError:
                    pass

            res = inputbar.handle_event(e)

            if not res:
                pass  
            elif isinstance(res, tuple) and len(res) == 2:
                kind, payload = res

                if kind == "attach":
                    picker.open()

                elif kind == "send" and payload and roster.selected_mac:
                    chat.send_text(roster.selected_mac, payload.strip())

                    attachments = picker.take_attachments()
                    for path in attachments:
                        try:
                            if hasattr(files, "send_path"):
                                files.send_path(roster.selected_mac, path)
                            elif hasattr(files, "send"):
                                files.send(roster.selected_mac, path)
                            else:
                                chat.send_text(roster.selected_mac, f"[adjunto seleccionado] {path}")
                        except Exception as ex:
                            chat.send_text(roster.selected_mac, f"[error adjunto] {path}: {ex}")

        # ----------------- EVENTOS (BACKEND → UI) -----------------
        pump.pump(bridge, max_events=300)

        # ----------------- RENDER -----------------
        w, h = screen.get_size()
        L = compute_layout(w, h)

        screen.fill(CLR["bg"])

        sidebar_rows = _build_sidebar_rows(roster.contacts, chat.messages_by_mac)
        sidebar.draw(screen, L, sidebar_rows)

        current_name = "Camilo"
        current_online = False
        if roster.selected_mac:
            for c in roster.contacts:
                if c.mac == roster.selected_mac:
                    current_name = c.name
                    current_online = c.online
                    break
        header.draw(screen, L, current_name, current_online)

        current_msgs = chat.messages_by_mac.get(roster.selected_mac or "", [])
        messages.draw(screen, L, [m.__dict__ for m in current_msgs])

        inputbar.draw(screen, L)

        manager.update(time_delta)
        manager.draw_ui(screen)

        pg.display.flip()

    pg.quit()
