import os
import time
import pygame as pg
import pygame_gui
from datetime import datetime
from typing import List, Dict
from collections import defaultdict

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
from components.composer import Composer
from components.input_bar import InputBar
from components.attachment_picker import AttachmentPicker
from state.models import ChatMessage, Contact


def _build_sidebar_rows(contacts: List[Contact], chat_messages: Dict[str, List[ChatMessage]]):
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

    # Suscribir FileService a eventos de transferencia (si existe helper)
    if hasattr(files, "register_event_handlers"):
        files.register_event_handlers(pump)

    # Fallback de eventos sin "type"
    if hasattr(pump, "fallback"):
        pump.fallback(lambda ev: None if (isinstance(ev, dict) and "type" not in ev)
                      else print("[UI] evento no manejado:", ev))

    sidebar = Sidebar()
    header = ChatHeader()
    messages = MessagesView()

    # InputBar sigue existiendo pero ahora lo envuelve Composer
    inputbar = InputBar(images_dir="images")
    composer = Composer(inputbar, images_dir="images")

    # ---- helpers tarjetas de archivo + progreso ----
    def now_hhmm():
        return datetime.now().strftime("%H:%M")

    # TX (yo envío)
    def append_local_file_card(to_mac: str, filename: str, subtitle: str = "Enviando…") -> ChatMessage:
        msg = ChatMessage(text="", time=now_hhmm(), side="tx")
        setattr(msg, "file", {"name": filename, "subtitle": subtitle})
        chat.messages_by_mac.setdefault(to_mac, []).append(msg)
        name_index_tx[filename].append(msg)
        return msg

    # RX (yo recibo)
    def append_incoming_file_card(from_mac: str, filename: str, subtitle: str = "Recibiendo…") -> ChatMessage:
        msg = ChatMessage(text="", time=now_hhmm(), side="rx")
        setattr(msg, "file", {"name": filename, "subtitle": subtitle})
        chat.messages_by_mac.setdefault(from_mac, []).append(msg)
        name_index_rx[(from_mac, filename)].append(msg)
        return msg

    def _update_msg_subtitle(msg: ChatMessage, subtitle: str):
        f = getattr(msg, "file", None)
        if isinstance(f, dict):
            f["subtitle"] = subtitle

    # Índices TX:
    progress_index_tx: Dict[str, ChatMessage] = {}     # file_id -> ChatMessage
    name_index_tx = defaultdict(list)                  # name -> [ChatMessage]
    rel_index_tx  = defaultdict(list)                  # rel  -> [ChatMessage] (si usas folder_send)
    last_tick_tx: Dict[str, float] = {}                # file_id -> last progress ts

    # Índices RX:
    progress_index_rx: Dict[str, ChatMessage] = {}     # file_id -> ChatMessage
    name_index_rx = defaultdict(list)                  # (from_mac, name) -> [ChatMessage]
    rel_index_rx  = defaultdict(list)                  # (from_mac, rel)  -> [ChatMessage]
    last_tick_rx: Dict[str, float] = {}                # file_id -> last progress ts

    # Watchdogs
    EPSILON_SECS = 1.0

    def _touch_tx(fid: str):
        if fid:
            last_tick_tx[fid] = time.time()

    def _touch_rx(fid: str):
        if fid:
            last_tick_rx[fid] = time.time()

    # ---------- Resolución de mensajes ----------
    def _resolve_msg_for_event_tx(ev: dict):
        fid = ev.get("file_id")
        if fid and fid in progress_index_tx:
            return progress_index_tx[fid]

        rel = ev.get("rel")
        if rel:
            lst = rel_index_tx.get(rel)
            if lst:
                m = lst[-1]
                if fid:
                    progress_index_tx[fid] = m
                return m

        name = ev.get("name")
        if name:
            lst = name_index_tx.get(name)
            if lst:
                m = lst[-1]
                if fid:
                    progress_index_tx[fid] = m
                return m

        return None

    def _resolve_msg_for_event_rx(ev: dict):
        fid = ev.get("file_id")
        if fid and fid in progress_index_rx:
            return progress_index_rx[fid]

        src = ev.get("src") or ev.get("from") or ev.get("sender")  # según backend
        rel = ev.get("rel")
        name = ev.get("name")

        if src and rel:
            lst = rel_index_rx.get((src, rel))
            if lst:
                m = lst[-1]
                if fid:
                    progress_index_rx[fid] = m
                return m

        if src and name:
            lst = name_index_rx.get((src, name))
            if lst:
                m = lst[-1]
                if fid:
                    progress_index_rx[fid] = m
                return m

        return None

    # ---------- Handlers TX (enviando) ----------
    def on_file_tx_started(ev: dict):
        msg = _resolve_msg_for_event_tx(ev)
        fid = ev.get("file_id")
        if msg and fid:
            progress_index_tx[fid] = msg
            _touch_tx(fid)

    def on_file_tx_progress(ev: dict):
        msg = _resolve_msg_for_event_tx(ev)
        if not msg:
            return
        fid = ev.get("file_id")
        if fid:
            _touch_tx(fid)

        pct = ev.get("percent")
        if pct is None:
            prog = ev.get("progress")
            if isinstance(prog, (int, float)):
                pct = prog * 100.0

        acked = ev.get("acked")
        total = ev.get("total") or 0

        if pct is None:
            subtitle = "Enviando…"
        else:
            pct_i = int(max(0, min(100, pct)))
            subtitle = f"{pct_i}% ({acked}/{total} chunks)" if (acked is not None and total) else f"{pct_i}%"

        _update_msg_subtitle(msg, subtitle)

    def on_file_tx_finished(ev: dict):
        msg = _resolve_msg_for_event_tx(ev)
        if msg:
            _update_msg_subtitle(msg, "Enviado")
        fid = ev.get("file_id")
        if fid:
            progress_index_tx.pop(fid, None)
            last_tick_tx.pop(fid, None)

    def on_file_tx_done(ev: dict):
        msg = _resolve_msg_for_event_tx(ev)
        if msg:
            _update_msg_subtitle(msg, "Enviado")
        fid = ev.get("file_id")
        if fid:
            progress_index_tx.pop(fid, None)
            last_tick_tx.pop(fid, None)

    def on_file_tx_error(ev: dict):
        msg = _resolve_msg_for_event_tx(ev)
        if msg:
            err = ev.get("error") or "Error"
            _update_msg_subtitle(msg, err)
        fid = ev.get("file_id")
        if fid:
            progress_index_tx.pop(fid, None)
            last_tick_tx.pop(fid, None)

    # ---------- Handlers RX (recibiendo) ----------
    def on_file_rx_started(ev: dict):
        """
        Esperado: {"type":"file_rx_started","file_id":"...","src":"aa:bb:...","name":"archivo.ext","rel":...}
        Creamos la tarjeta en el hilo con el MAC del remitente (side="rx").
        """
        src = ev.get("src") or ev.get("from") or ev.get("sender")
        name = ev.get("name") or "archivo"
        if not src:
            return
        msg = append_incoming_file_card(src, name, "Recibiendo…")
        # indexaciones auxiliares
        rel = ev.get("rel")
        if rel:
            rel_index_rx[(src, rel)].append(msg)
        progress_index_rx[ev.get("file_id", "")] = msg
        _touch_rx(ev.get("file_id", ""))

    def on_file_rx_progress(ev: dict):
        msg = _resolve_msg_for_event_rx(ev)
        if not msg:
            return
        fid = ev.get("file_id")
        if fid:
            _touch_rx(fid)

        pct = ev.get("percent")
        if pct is None:
            prog = ev.get("progress")
            if isinstance(prog, (int, float)):
                pct = prog * 100.0

        acked = ev.get("acked")
        total = ev.get("total") or 0

        if pct is None:
            subtitle = "Recibiendo…"
        else:
            pct_i = int(max(0, min(100, pct)))
            subtitle = f"{pct_i}% ({acked}/{total} chunks)" if (acked is not None and total) else f"{pct_i}%"

        _update_msg_subtitle(msg, subtitle)

    def on_file_rx_finished(ev: dict):
        msg = _resolve_msg_for_event_rx(ev)
        if msg:
            _update_msg_subtitle(msg, "Recibido")
        fid = ev.get("file_id")
        if fid:
            progress_index_rx.pop(fid, None)
            last_tick_rx.pop(fid, None)

    def on_file_rx_done(ev: dict):
        msg = _resolve_msg_for_event_rx(ev)
        if msg:
            _update_msg_subtitle(msg, "Recibido")
        fid = ev.get("file_id")
        if fid:
            progress_index_rx.pop(fid, None)
            last_tick_rx.pop(fid, None)

    def on_file_rx_error(ev: dict):
        msg = _resolve_msg_for_event_rx(ev)
        if msg:
            err = ev.get("error") or "Error"
            _update_msg_subtitle(msg, err)
        fid = ev.get("file_id")
        if fid:
            progress_index_rx.pop(fid, None)
            last_tick_rx.pop(fid, None)

    # Suscripciones a eventos de archivo
    pump.subscribe("file_tx_started",  on_file_tx_started)
    pump.subscribe("file_tx_progress", on_file_tx_progress)
    pump.subscribe("file_tx_finished", on_file_tx_finished)
    pump.subscribe("file_tx_done",     on_file_tx_done)   # compat
    pump.subscribe("file_tx_error",    on_file_tx_error)

    pump.subscribe("file_rx_started",  on_file_rx_started)
    pump.subscribe("file_rx_progress", on_file_rx_progress)
    pump.subscribe("file_rx_finished", on_file_rx_finished)
    pump.subscribe("file_rx_done",     on_file_rx_done)   # compat
    pump.subscribe("file_rx_error",    on_file_rx_error)

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

                # Sidebar: selección de contacto
                try:
                    w, h = screen.get_size()
                    L = compute_layout(w, h)
                    maybe_mac = sidebar.handle_event(e, L, roster.contacts)
                    if maybe_mac:
                        roster.select(maybe_mac)
                except TypeError:
                    pass

            # Composer gestiona barra + chips
            res = composer.handle_event(e)

            if not res:
                pass
            else:
                kind, payload = res

                if kind == "attach":
                    picker.open()

                elif kind == "send" and roster.selected_mac:
                    # payload = {"text": str, "files": [str,...]}
                    text_to_send = (payload.get("text") or "").strip()
                    files_to_send = payload.get("files") or []

                    if text_to_send:
                        chat.send_text(roster.selected_mac, text_to_send)

                    for path in files_to_send:
                        try:
                            filename = os.path.basename(path)
                            # 1) Eco local TX
                            msg = append_local_file_card(roster.selected_mac, filename, "Enviando…")
                            # 2) Envío real
                            returned_id = None
                            if hasattr(files, "send_path"):
                                returned_id = files.send_path(roster.selected_mac, path)
                            elif hasattr(files, "send"):
                                returned_id = files.send(roster.selected_mac, path)
                            else:
                                chat.send_text(roster.selected_mac, f"[adjunto] {path}")

                            if isinstance(returned_id, str) and returned_id:
                                progress_index_tx[returned_id] = msg
                                _touch_tx(returned_id)

                        except Exception as ex:
                            chat.send_text(roster.selected_mac, f"[error adjunto] {path}: {ex}")

        # ----------------- EVENTOS (BACKEND → UI) -----------------
        pump.pump(bridge, max_events=300)

        # ----------------- WATCHDOGS -----------------
        now = time.time()
        # TX: marca Enviado si no hay progreso hace ε seg.
        for fid, msg in list(progress_index_tx.items()):
            ts = last_tick_tx.get(fid)
            if ts is not None and (now - ts) > EPSILON_SECS:
                _update_msg_subtitle(msg, "Enviado")
                progress_index_tx.pop(fid, None)
                last_tick_tx.pop(fid, None)
        # RX: marca Recibido si no hay progreso hace ε seg.
        for fid, msg in list(progress_index_rx.items()):
            ts = last_tick_rx.get(fid)
            if ts is not None and (now - ts) > EPSILON_SECS:
                _update_msg_subtitle(msg, "Recibido")
                progress_index_rx.pop(fid, None)
                last_tick_rx.pop(fid, None)

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

        # Barra + chips de adjuntos
        composer.draw(screen, L)

        # UI Manager + File dialog
        manager.update(time_delta)
        picker.update(time_delta)

        # Si el file dialog devolvió rutas, agrégalas como chips
        new_files = picker.take_attachments()
        if new_files:
            composer.add_files(new_files)

        manager.draw_ui(screen)
        pg.display.flip()

    pg.quit()
