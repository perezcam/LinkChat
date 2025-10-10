import os
import pygame as pg
from core.theme import CLR
from core.draw import rounded_rect, text

class InputBar:
    def __init__(self, images_dir="images"):
        self.value = ""
        self.focus = False
        self._cursor_on = True
        self._cursor_t = 0
        self.images_dir = images_dir
        self._icons = {"attach": None, "send": None}
        self._icon_scaled_cache = {}
        self._last_btn_size = None
        self._r = None
        self._r_edit = None
        self._r_btn_left = None
        self._r_btn_right = None

    # ---------- helpers ----------
    def _load_icons(self):
        def load(name):
            p = os.path.join(self.images_dir, f"{name}.svg")
            surf = pg.image.load(p).convert_alpha()
            return surf
        self._icons["attach"] = load("attach")
        self._icons["send"]   = load("send")

    def _ensure_scaled_icons(self, btn_size):
        # rehace el cache si cambia el tamaño de botón
        if self._last_btn_size == btn_size and self._icon_scaled_cache:
            return
        self._icon_scaled_cache = {
            k: pg.transform.smoothscale(v, (btn_size, btn_size))
            for k, v in self._icons.items()
        }
        self._last_btn_size = btn_size

    def _compute_rects(self, L):
        """Calcula y guarda los rects: barra, edit, botones."""
        pad = L["pad"]
        s   = L["s"]
        r_content = L.get("chat", L.get("content", L["sidebar"])) 

        h = int(56 * s)                        
        r = pg.Rect(
            r_content.x + pad,
            r_content.bottom - pad - h,
            r_content.w - 2 * pad,
            h
        )
        ip = int(12 * s)                        # padding interno
        btn = h - 2 * ip                        # boton cuadrado
        self._ensure_scaled_icons(btn)

        r_btn_left  = pg.Rect(r.x + ip,         r.y + ip, btn, btn)
        r_btn_right = pg.Rect(r.right - ip - btn, r.y + ip, btn, btn)

        r_edit = pg.Rect(r_btn_left.right + ip, r.y + ip,
                         r_btn_right.left - ip - (r_btn_left.right + ip),
                         btn)

        self._r, self._r_edit = r, r_edit
        self._r_btn_left, self._r_btn_right = r_btn_left, r_btn_right

    # ---------- API ----------
    def handle_event(self, e):
        """
        Devuelve:
          - ("attach", None) si click en adjuntar
          - ("send", text)   si click en enviar o Enter
          - None en el resto de casos
        """
        if self._r is None:
            return None  

        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
            if self._r.collidepoint(e.pos):
                self.focus = True
                if self._r_btn_left.collidepoint(e.pos):
                    return ("attach", None)
                if self._r_btn_right.collidepoint(e.pos):
                    txt = self.value.strip()
                    if txt:
                        self.value = ""
                        return ("send", txt)
            else:
                self.focus = False
            return None

        if e.type == pg.KEYDOWN and self.focus:
            if e.key in (pg.K_RETURN, pg.K_KP_ENTER):
                txt = self.value.strip()
                if txt:
                    self.value = ""
                    return ("send", txt)
                return None
            if e.key == pg.K_BACKSPACE:
                self.value = self.value[:-1]
                return None
            if e.key == pg.K_v and (pg.key.get_mods() & pg.KMOD_CTRL):
                try:
                    clip = pg.scrap.get(pg.SCRAP_TEXT)
                    if clip:
                        self.value += clip.decode("utf-8")
                except Exception:
                    pass
                return None
            # texto imprimible
            if e.unicode and not e.key in (pg.K_LCTRL, pg.K_RCTRL, pg.K_LALT, pg.K_RALT):
                self.value += e.unicode
                return None

        return None

    def draw(self, surf, L):
        if self._icons["attach"] is None:
            self._load_icons()

        # rects
        self._compute_rects(L)
        r, r_edit = self._r, self._r_edit
        r_btn_left, r_btn_right = self._r_btn_left, self._r_btn_right

        # barra
        rounded_rect(surf, r, CLR["panel"], L["r_sm"])

        # botón adjuntar (izquierda)
        rounded_rect(surf, r_btn_left, CLR["panel"], L["r_sm"])
        surf.blit(self._icon_scaled_cache["attach"], r_btn_left)

        # botón enviar (derecha)
        rounded_rect(surf, r_btn_right, CLR["panel"], L["r_sm"])
        surf.blit(self._icon_scaled_cache["send"], r_btn_right)

        # área de texto
        rounded_rect(surf, r_edit, CLR["surface_alt"], L["r_sm"])

        # placeholder / texto
        f = L["fonts"]
        pad_txt = int(10 * L["s"])
        placeholder = "Type a message..."
        show = self.value if self.value else placeholder
        color = CLR["text"] if self.value else CLR["muted"]

        # recortar para no pintar fuera del input
        prev_clip = surf.get_clip()
        surf.set_clip(r_edit)
        text(surf, show, f["p"], color, (r_edit.x + pad_txt, r_edit.centery), "midleft")

        # cursor parpadeante si hay foco
        self._cursor_t = (self._cursor_t + 1) % 60
        self._cursor_on = self._cursor_t < 30
        if self.focus and self._cursor_on:
            # mide ancho del texto actual
            # (si tienes un helper de medir texto úsalo; aquí usamos render rápido)
            tw = f["p"].render(self.value or "", True, (0,0,0)).get_width()
            cx = r_edit.x + pad_txt + tw + 2
            cy1, cy2 = r_edit.y + 8, r_edit.bottom - 8
            pg.draw.line(surf, CLR["muted"], (cx, cy1), (cx, cy2), 2)

        surf.set_clip(prev_clip)
