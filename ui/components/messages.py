from core.theme import CLR
from core.draw import rounded_rect, text
import pygame as pg
import os

class MessagesView:
    def __init__(self, images_dir="images"):
        self.wrap_cache = {}
        self.images_dir = images_dir
        self._icons = {"file": None}            
        self._icon_scaled_cache = {}            

    # --- helpers de iconos (mismo patrón que InputBar) ---
    def _load_icons(self):
        def load(name: str) -> pg.Surface:
            # intenta SVG y si no existe, PNG
            p_svg = os.path.join(self.images_dir, f"{name}.svg")
            p_png = os.path.join(self.images_dir, f"{name}.png")
            path = p_svg if os.path.exists(p_svg) else p_png
            if not os.path.exists(path):
                raise FileNotFoundError(f"Icono no encontrado: {p_svg} ni {p_png}")
            return pg.image.load(path).convert_alpha()
        self._icons["file"] = load("file")

    def _ensure_icon_scaled(self, name: str, size_px: int) -> pg.Surface:
        if self._icons["file"] is None:
            self._load_icons()
        key = (name, size_px)
        if key in self._icon_scaled_cache:
            return self._icon_scaled_cache[key]
        base = self._icons[name]
        scaled = pg.transform.smoothscale(base, (size_px, size_px))
        self._icon_scaled_cache[key] = scaled
        return scaled

    # --- helpers de texto ---
    def _wrap(self, font, body, maxw):
        key = (id(font), body, maxw)
        cached = self.wrap_cache.get(key)
        if cached:
            return cached
        words = body.split(" ")
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if font.size(test)[0] <= maxw:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        self.wrap_cache[key] = lines
        return lines

    # --- tarjeta de archivo ---
    def _draw_file_card(self, surf, L, m, x_left, x_right, y):
        f = L["fonts"]; s = L["s"]
        is_tx = (m.get("side") == "tx")
        fileinfo = m.get("file") or {}

        name = fileinfo.get("name", "archivo")
        subtitle = fileinfo.get("subtitle") or fileinfo.get("rel") or "Toca para abrir"

        maxw = min(L["bubble_max"], int(L["messages"].w * 0.48))
        pad_bub = int(12 * s)
        fh = f["p"].get_linesize()

        card_h = int(fh * 2.2 + pad_bub * 2)
        bw = int(maxw)
        bx = (x_right - bw) if is_tx else x_left

        color = CLR["primary"] if is_tx else CLR["bubble_rx"]
        fg = CLR["primary_fg"] if is_tx else CLR["text"]

        br = pg.Rect(int(bx), int(y), int(bw), int(card_h))
        rounded_rect(surf, br, color, L["r_lg"])

        # icono de archivo (cargado como en InputBar)
        icon_size = fh + 8
        icon_surf = self._ensure_icon_scaled("file", icon_size)
        icon_rect = icon_surf.get_rect()
        icon_rect.topleft = (br.x + pad_bub, br.y + pad_bub)
        surf.blit(icon_surf, icon_rect)

        # textos
        text(surf, name, f["p"], fg, (icon_rect.right + 10, icon_rect.y))
        text(surf, subtitle, f["xs"], fg, (icon_rect.right + 10, icon_rect.y + fh + 2))

        # hora
        ts_color = fg if is_tx else (113, 113, 130)
        text(surf, m.get("time", ""), f["xs"], ts_color, (br.x + pad_bub, br.bottom - pad_bub))

        return br.bottom + int(16 * s)

    # --- render general ---
    def draw(self, surf, L, messages):
        r = L["messages"]; pad = L["pad"]; f = L["fonts"]
        x_left  = r.x + pad * 2
        x_right = r.right - pad * 2
        y = r.y + pad

        for m in messages:
            # Tarjeta de archivo con icono real
            if m.get("file"):
                y = self._draw_file_card(surf, L, m, x_left, x_right, y)
                continue

            # Mensaje de texto
            is_tx = (m.get("side") == "tx")
            body = m.get("text", "")
            font = f["p"]
            maxw = min(L["bubble_max"], r.w * 0.48)
            lines = self._wrap(font, body, maxw)
            text_w = max(font.size(line)[0] for line in lines) if lines else 0

            pad_bub = int(12 * L["s"])
            text_h = (len(lines) * font.get_linesize()) if lines else font.get_linesize()

            # ancho mínimo (≈ 6 letras anchas)
            min_chars = 6
            min_text_w = font.size("M" * min_chars)[0]
            min_bw = int(min_text_w + pad_bub * 2)

            # ancho por contenido
            bw_auto = int(text_w + pad_bub * 2)

            # respetar máximo y mínimo
            bw = max(min_bw, min(bw_auto, int(maxw)))

            bh = int(text_h + pad_bub * 2)
            bx = (x_right - bw) if is_tx else x_left

            color = CLR["primary"] if is_tx else CLR["bubble_rx"]
            fg = CLR["primary_fg"] if is_tx else CLR["text"]

            br = pg.Rect(int(bx), int(y), int(bw), int(bh))
            rounded_rect(surf, br, color, L["r_lg"])

            ty = br.y + pad_bub
            for line in lines:
                text(surf, line, font, fg, (br.x + pad_bub, ty))
                ty += font.get_linesize()

            ts_color = (fg if is_tx else (113, 113, 130))
            text(surf, m.get("time", ""), f["xs"], ts_color, (br.x + pad_bub, br.bottom - pad_bub))

            y = br.bottom + int(16 * L["s"])
