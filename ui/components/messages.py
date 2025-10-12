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

    # ----------------------------
    # helpers de texto 
    # ----------------------------
    def _wrap(self, font, body: str, maxw: int):
        """
        Envuelve por palabras respetando saltos de línea (\n).
        Si una 'palabra' es más ancha que maxw (URLs, hashes), la parte en segmentos
        que quepan por ancho. Cachea por (font, body, maxw).
        """
        key = (id(font), body, maxw)
        cached = self.wrap_cache.get(key)
        if cached:
            return cached

        if not body:
            self.wrap_cache[key] = [""]
            return [""]

        out_lines = []

        for para in body.split("\n"):
            # Párrafo vacío
            if para == "":
                out_lines.append("")
                continue

            words = para.split(" ")
            cur = ""

            for w in words:
              
                test = (cur + " " + w).strip() if cur else w
                if font.size(test)[0] <= maxw:
                    cur = test
                    continue

                if cur:
                    out_lines.append(cur)
                    cur = ""

                if font.size(w)[0] > maxw:
                    i = 0
                    n = len(w)
                    while i < n:
                        lo, hi = 1, n - i
                        best = 1
                        while lo <= hi:
                            mid = (lo + hi) // 2
                            if font.size(w[i:i+mid])[0] <= maxw:
                                best = mid
                                lo = mid + 1
                            else:
                                hi = mid - 1
                        out_lines.append(w[i:i+best])
                        i += best
                else:
                    cur = w

            if cur:
                out_lines.append(cur)

        self.wrap_cache[key] = out_lines
        return out_lines

    # ----------------------------
    # tarjeta de archivo
    # ----------------------------
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

        icon_size = fh + 8
        icon_surf = self._ensure_icon_scaled("file", icon_size)
        icon_rect = icon_surf.get_rect()
        icon_rect.topleft = (br.x + pad_bub, br.y + pad_bub)
        surf.blit(icon_surf, icon_rect)

        text(surf, name, f["p"], fg, (icon_rect.right + 10, icon_rect.y))
        text(surf, subtitle, f["xs"], fg, (icon_rect.right + 10, icon_rect.y + fh + 2))

        # hora
        ts_color = fg if is_tx else (113, 113, 130)
        text(surf, m.get("time", ""), f["xs"], ts_color, (br.x + pad_bub, br.bottom - pad_bub))

        return br.bottom + int(16 * s)

    # ----------------------------
    # render general
    # ----------------------------
    def draw(self, surf, L, messages):
        r = L["messages"]; pad = L["pad"]; f = L["fonts"]
        x_left  = r.x + pad * 2
        x_right = r.right - pad * 2
        y = r.y + pad

        for m in messages:
            if m.get("file"):
                y = self._draw_file_card(surf, L, m, x_left, x_right, y)
                continue

            is_tx = (m.get("side") == "tx")
            body = m.get("text", "") or ""
            font = f["p"]

            # ampliar ancho efectivo para favorecer el wrap vertical
            maxw = int(min(L["bubble_max"], r.w * 0.7))

            lines = self._wrap(font, body, maxw)
            # ancho real del texto para ajustar burbuja
            text_w = max((font.size(line)[0] for line in lines), default=0)

            pad_bub = int(12 * L["s"])
            line_h = font.get_linesize()
            text_h = max(line_h, len(lines) * line_h)

            # ancho mínimo
            min_chars = 6
            min_text_w = font.size("M" * min_chars)[0]
            min_bw = int(min_text_w + pad_bub * 2)

            # ancho por contenido
            bw_auto = int(text_w + pad_bub * 2)

            # respetar máximo y mínimo
            bw = max(min_bw, min(bw_auto, int(maxw)))

            # alto por contenido (burbuja crece hacia abajo)
            bh = int(text_h + pad_bub * 2)
            bx = (x_right - bw) if is_tx else x_left

            color = CLR["primary"] if is_tx else CLR["bubble_rx"]
            fg = CLR["primary_fg"] if is_tx else CLR["text"]

            br = pg.Rect(int(bx), int(y), int(bw), int(bh))
            rounded_rect(surf, br, color, L["r_lg"])

            ty = br.y + pad_bub
            for line in lines:
                text(surf, line, font, fg, (br.x + pad_bub, ty))
                ty += line_h

            ts_color = (fg if is_tx else (113, 113, 130))
            text(surf, m.get("time", ""), f["xs"], ts_color, (br.x + pad_bub, br.bottom - pad_bub))

            y = br.bottom + int(16 * L["s"])
