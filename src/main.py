import os
import logging
import signal
import sys
import time
import threading
import shlex
import contextlib
from datetime import datetime

from src.messaging.service_messaging import Messaging
from src.core.managers.raw_socket import SocketManager
from src.core.managers.service_threads import ThreadManager
from src.discover.discover import Discovery
from src.prepare.network_config import get_runtime_config

# ========= Ajustes terminal / modo UI =========
os.environ.setdefault("TERM", "xterm")
os.environ.setdefault("LANG", "C.UTF-8")
UI_MODE = os.getenv("UI_MODE", "auto").strip().lower()

try:
    import curses
except Exception:
    curses = None

HELP_FOOTER = "↑/↓ seleccionar • Enter: escribir/enviar • Esc: cancelar • q: salir"

# ==================================================
#                TUI (curses) – Solo tabla
# ==================================================
class NeighborTableUI:
    def __init__(self, *, alias, local_mac, interface, ethertype, neighbors_ref, messaging: Messaging):
        self.alias = alias
        self.local_mac = local_mac
        self.interface = interface
        self.ethertype = ethertype
        self.neighbors = neighbors_ref
        self.messaging = messaging
        self._running = True

        # Estado de interacción
        self._selected = 0         # índice de fila
        self._typing = False       # ¿está escribiendo un mensaje?
        self._input = ""           # buffer de texto
        self._status = ""          # mensaje corto de estado
        self._status_until = 0.0

    def on_neighbors_changed(self, _):  # la TUI refresca sola
        pass

    def push_incoming(self, mac: str, payload: bytes):
        # Notificación simple en el footer (sin lista de logs)
        alias = self.neighbors.get(mac, {}).get("alias", "?")
        text = payload.decode("utf-8", errors="replace")
        self._status_set(f"← {alias} ({mac}): {text}", ttl=4.0)


    def _status_set(self, msg: str, ttl=2.0):
        self._status = msg
        self._status_until = time.time() + ttl

    def run(self):
        print("[UI=cli] listo. Mostrando tabla…", flush=True)
        if curses is None:
            raise RuntimeError("curses no disponible")
        curses.wrapper(self._main)

    # ----------------- bucle principal -----------------
    def _main(self, stdscr):
        stdscr.nodelay(True)
        try:
            curses.curs_set(0)
        except Exception:
            pass

        last_draw = 0.0
        while self._running:
            ch = -1
            try:
                ch = stdscr.getch()
            except Exception:
                pass

            if ch != -1:
                self._handle_key(ch)

            now = time.time()
            if now - last_draw >= 0.15:
                self._draw(stdscr)
                last_draw = now
            time.sleep(0.02)

    # ----------------- entrada teclado -----------------
    def _handle_key(self, ch: int):
        if self._typing:
            # Modo de escritura del mensaje
            if ch in (27,):  # Esc -> cancelar
                self._typing = False
                self._input = ""
                return
            if ch in (10, 13):  # Enter -> enviar
                self._send_current()
                self._input = ""
                self._typing = False
                return
            if ch in (curses.KEY_BACKSPACE, 127, 8):
                self._input = self._input[:-1]
                return
            if 32 <= ch <= 126:  # imprimibles
                self._input += chr(ch)
            return

        # Modo navegación
        if ch in (ord('q'), ord('Q')):
            self._running = False
            return
        if ch in (curses.KEY_UP, ord('k')):
            self._selected = max(0, self._selected - 1)
            return
        if ch in (curses.KEY_DOWN, ord('j')):
            self._selected = min(max(0, len(self._rows()) - 1), self._selected + 1)
            return
        if ch in (10, 13, ord('m'), ord('M')):  # Enter o 'm' -> empezar a escribir
            if self._rows():
                self._typing = True
                self._input = ""
            return

    # ----------------- datos tabla -----------------
    def _rows(self):
        # snapshot ordenado por más recientes
        now = time.time()
        rows = []
        for mac, meta in list(self.neighbors.items()):
            alias = meta.get("alias", "?")
            age = int(max(0, now - meta.get("last_seen", 0)))
            rows.append((mac, alias, age))
        rows.sort(key=lambda r: r[2])  # menor age primero
        return rows

    # ----------------- envío -----------------
    def _send_current(self):
        rows = self._rows()
        if not rows:
            self._status_set("No hay vecinos.")
            return
        msg = self._input.strip()
        if not msg:
            self._status_set("Mensaje vacío.")
            return
        idx = max(0, min(self._selected, len(rows) - 1))
        mac, alias, _ = rows[idx]
        try:
            self.messaging.send_to_mac(mac, msg.encode("utf-8"))
            self._status_set(f"Enviado a {alias} ({mac}).")
        except Exception as e:
            self._status_set(f"Error al enviar: {e}", ttl=3.0)

    # ----------------- util render seguro -----------------
    @staticmethod
    def _fit_cols(total_width: int):
        """
        Calcula anchos seguros (nunca negativos) para columnas:
        # | MAC | Alias | Visto hace
        Devuelve lista de anchos [w#, wmac, walias, wage]
        """
        # mínimos razonables
        min_hash, min_mac, min_alias, min_age = 4, 19, 8, 10
        # separadores y espacios: tenemos 3 separadores " | " (~3*3=9) + espacios iniciales
        sep_cost = 3 * 3 + 1  # " " + "| " tres veces
        base_min = min_hash + min_mac + min_alias + min_age + sep_cost
        width = max(total_width, base_min)

        # presupuesto extra para repartir
        extra = width - sep_cost
        # arranque con mínimos
        w_hash = min_hash
        w_mac = min_mac
        w_alias = min_alias
        w_age = min_age

        # reparte extra priorizando alias y MAC
        remaining = extra - (w_hash + w_mac + w_alias + w_age)
        if remaining > 0:
            take = min(remaining, 20); w_alias += take; remaining -= take
        if remaining > 0:
            take = min(remaining, 8); w_mac += take; remaining -= take
        if remaining > 0:
            take = min(remaining, 4); w_age += take; remaining -= take
        if remaining > 0:
            w_hash += remaining

        return [w_hash, w_mac, w_alias, w_age]

    # ----------------- pintado -----------------
    def _draw(self, stdscr):
        stdscr.erase()
        H, W = stdscr.getmaxyx()
        now = time.time()

        # Cabecera compacta
        header = f"{self.alias}  |  IF={self.interface}  |  MAC={self.local_mac}  |  EtherType=0x{self.ethertype:04X}  |  {datetime.now().strftime('%H:%M:%S')}"
        stdscr.addnstr(0, 0, header[:W].ljust(W), W)

        # Línea separadora
        try:
            stdscr.hline(1, 0, curses.ACS_HLINE, W)
        except Exception:
            stdscr.addnstr(1, 0, "-" * W, W)

        # Título
        stdscr.addnstr(2, 0, " Vecinos ", W)

        # Encabezados y columnas (cálculo seguro de anchos)
        try:
            stdscr.hline(3, 0, curses.ACS_HLINE, W)
        except Exception:
            stdscr.addnstr(3, 0, "-" * W, W)

        rows = self._rows()
        colW = self._fit_cols(W)
        w_hash, w_mac, w_alias, w_age = colW

        # header fila
        head = (
            f" {'#':<{w_hash-2}}| "
            f"{'MAC':<{w_mac-2}}| "
            f"{'Alias':<{w_alias-2}}| "
            f"{'Visto hace':<{w_age-2}}"
        )
        stdscr.addnstr(4, 0, head[:W].ljust(W), W)

        try:
            stdscr.hline(5, 0, curses.ACS_HLINE, W)
        except Exception:
            stdscr.addnstr(5, 0, "-" * W, W)

        # Render filas
        start_y = 6
        max_rows = max(1, H - 10)  # deja espacio a input y footer
        for i in range(min(len(rows), max_rows)):
            mac, alias, age = rows[i]
            ncol0 = f"{i+1:>2}"
            ncol1 = mac
            ncol2 = alias or "?"
            ncol3 = f"{age:>4}s"

            # recortes duros para no desbordar
            ncol0 = ncol0[:max(0, w_hash-2)]
            ncol1 = ncol1[:max(0, w_mac-2)]
            ncol2 = ncol2[:max(0, w_alias-2)]
            ncol3 = ncol3[:max(0, w_age-2)]

            line = (
                f" {ncol0:<{max(1, w_hash-2)}}| "
                f"{ncol1:<{max(1, w_mac-2)}}| "
                f"{ncol2:<{max(1, w_alias-2)}}| "
                f"{ncol3:<{max(1, w_age-2)}}"
            )

            if i == self._selected:
                stdscr.addnstr(start_y + i, 0, line[:W].ljust(W), W, curses.A_REVERSE)
            else:
                stdscr.addnstr(start_y + i, 0, line[:W].ljust(W), W)

        # Si no hay vecinos
        if not rows:
            stdscr.addnstr(start_y, 0, "(sin vecinos descubiertos)".ljust(W), W)

        # Línea separadora superior de input
        try:
            stdscr.hline(H - 3, 0, curses.ACS_HLINE, W)
        except Exception:
            stdscr.addnstr(H - 3, 0, "-" * W, W)

        # Input / Estado
        if self._typing:
            sel_txt = "todos" if not rows else f"{rows[self._selected][1]} ({rows[self._selected][0]})"
            prompt = f"Mensaje para {sel_txt}: {self._input}"
            stdscr.addnstr(H - 2, 0, prompt[:W].ljust(W), W)
            stdscr.addnstr(H - 1, 0, "Enter: enviar • Esc: cancelar".ljust(W), W)
        else:
            status = self._status if now < self._status_until else ""
            stdscr.addnstr(H - 2, 0, status[:W].ljust(W), W)
            stdscr.addnstr(H - 1, 0, HELP_FOOTER[:W].ljust(W), W)

        stdscr.refresh()


# ==================================================
#              CLI (fallback sin curses)
# ==================================================
class CLIMenuUI:
    """
    UI textual sin logs:
    - Imprime tabla de vecinos como tabla ascii
    - Permite enviar: escribe 'n <mensaje>' (n = número de fila)
      Ej: "1 hola nodo"  -> envía al vecino #1
      Comandos: 'r' refrescar, 'q' salir
    """
    def __init__(self, *, neighbors_ref, messaging: Messaging):
        self.neighbors = neighbors_ref
        self.messaging = messaging
        self._running = True
        self._last_snapshot = ()

    def on_neighbors_changed(self, _):
        self._print_table()

    def push_incoming(self, mac: str, payload: bytes):
        # Mostrar línea de mensaje entrante, pero sin “logs” del sistema
        text = payload.decode("utf-8", errors="replace")
        alias = self.neighbors.get(mac, {}).get("alias", "?")
        print(f"[{time.strftime('%H:%M:%S')}] ← {alias} ({mac}): {text}", flush=True)


    def _rows(self):
        now = time.time()
        rows = []
        for mac, meta in list(self.neighbors.items()):
            alias = meta.get("alias", "?")
            age = int(max(0, now - meta.get("last_seen", 0)))
            rows.append((mac, alias, age))
        rows.sort(key=lambda r: r[2])
        return rows

    def _print_table(self):
        rows = self._rows()
        snap = tuple(rows)
        if snap == self._last_snapshot:
            return
        self._last_snapshot = snap

        # Tabla ASCII
        print()
        print("+----+-------------------+--------------------------+------------+")
        print("| #  | MAC               | Alias                    | Visto hace |")
        print("+----+-------------------+--------------------------+------------+")
        for i, (mac, alias, age) in enumerate(rows, 1):
            print(f"| {i:>2} | {mac:<17} | {alias:<24} | {age:>4}s      |")
        if not rows:
            print("| -- | (sin vecinos)     |                          |            |")
        print("+----+-------------------+--------------------------+------------+")
        print("Escribe: <#> <mensaje>   |  r: refrescar  |  q: salir")

    def run(self):
        self._print_table()
        while self._running:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line.lower() in ("q", "quit", "exit"):
                break
            if line.lower() in ("r", "refrescar"):
                self._print_table()
                continue

            parts = shlex.split(line)
            if parts and parts[0].isdigit():
                idx = int(parts[0]) - 1
                msg = " ".join(parts[1:]) if len(parts) > 1 else ""
                rows = self._rows()
                if not (0 <= idx < len(rows)):
                    print("Fila inválida.")
                    continue
                if not msg:
                    print("Mensaje vacío.")
                    continue
                mac, alias, _ = rows[idx]
                try:
                    self.messaging.send_to_mac(mac, msg.encode("utf-8"))
                    print(f"Enviado a {alias} ({mac}).")
                except Exception as e:
                    print(f"Error al enviar: {e}")
                continue

            print("Entrada no válida. Usa: <#> <mensaje>  |  r  |  q")


# ==================================================
#                     MAIN
# ==================================================
def main():
    # 1) Logging SOLO a archivo (la UI queda limpia)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - [pid=%(process)d] %(message)s",
        handlers=[logging.FileHandler("app.log", encoding="utf-8")],
        force=True
    )

    cfg = get_runtime_config()   # respeta tu lógica original (env + autodetección)
    INTERFACE  = cfg["interface"]
    ALIAS      = cfg["alias"]
    ETHER_TYPE = cfg["ethertype"]

    # Señales
    signal.signal(signal.SIGINT, lambda s, f: None)
    signal.signal(signal.SIGTERM, lambda s, f: None)

    # 2) Arranque servicios
    try:
        with SocketManager(interface=INTERFACE, ethertype=ETHER_TYPE) as sock:
            thmgr = ThreadManager(socket_manager=sock); thmgr.start()
            discover = Discovery(service_threads=thmgr, alias=ALIAS, interval_seconds=5.0); discover.attach()
            messaging = Messaging(threads=thmgr, neighbors_ref=discover.neighbors); messaging.attach()

            # 3) Selección de UI
            has_tty = sys.stdin.isatty() and sys.stdout.isatty()
            use_curses = (UI_MODE == "curses") or (UI_MODE == "auto" and curses is not None and has_tty)

            if use_curses:
                ui = NeighborTableUI(
                    alias=ALIAS, local_mac=sock.mac, interface=INTERFACE, ethertype=ETHER_TYPE,
                    neighbors_ref=discover.neighbors, messaging=messaging
                )
            else:
                ui = CLIMenuUI(neighbors_ref=discover.neighbors, messaging=messaging)

            discover.set_on_neighbors_changed(ui.on_neighbors_changed)
            messaging.on_message(lambda frame, src_mac, payload: ui.push_incoming(src_mac, payload))

            try:
                ui.run()
            finally:
                thmgr.stop()
                with contextlib.suppress(Exception): discover.detach()
                with contextlib.suppress(Exception): messaging.detach()

    except PermissionError:
        logging.error("Permisos insuficientes para raw sockets (usa sudo o capabilities).")
        sys.exit(1)
    except OSError as e:
        logging.error(f"Error al abrir el socket: {e}")
        sys.exit(1)
    except Exception as e:
        logging.exception(f"Error inesperado en main: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
