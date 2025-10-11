import os
import pygame as pg
from core.theme import CLR
from core.draw import rounded_rect, text, divider, dot
from state.models import Contact

class Sidebar:
    def __init__(self, images_dir: str = "images"):
        self.selected = 0
        self.scroll = 0

        self._icon_brand = None
        p_brand = os.path.join(images_dir, "enredate.svg")
        try:
            self._icon_brand = pg.image.load(p_brand).convert_alpha()
        except Exception:
            surf = pg.Surface((24, 24), pg.SRCALPHA)
            pg.draw.rect(surf, CLR.get("accent", (120, 120, 120)), surf.get_rect(), border_radius=6)
            self._icon_brand = surf

        self._icon_all = None
        p_all = os.path.join(images_dir, "all.svg")
        try:
            self._icon_all = pg.image.load(p_all).convert_alpha()
        except Exception:
            surf = pg.Surface((24, 24), pg.SRCALPHA)
            pg.draw.circle(surf, CLR.get("accent", (120, 120, 120)), (12, 12), 10)
            self._icon_all = surf

        self._icon_user = None
        p_user = os.path.join(images_dir, "user.svg")
        try:
            self._icon_user = pg.image.load(p_user).convert_alpha()
        except Exception:
            self._icon_user = None

    #  Helpers internos 
    def _item_h(self, L) -> int:
        return int(68 * L["s"])

    def _search_rect(self, L) -> pg.Rect:
        r = L["sidebar"]; pad = L["pad"]; f = L["fonts"]
        return pg.Rect(
            r.x + pad,
            r.y + pad*2 + f["h2"].get_linesize(),
            r.w - pad*2,
            int(40 * L["s"])
        )

    def _list_start_y(self, L) -> int:
        return self._search_rect(L).bottom + L["pad"]

    def _list_view_height(self, L) -> int:
        r = L["sidebar"]; pad = L["pad"]
        btn_h = int(50 * L["s"])
        return r.h - ((self._list_start_y(L) - r.y) + pad + btn_h)

    def _max_scroll(self, L, n_items: int) -> int:
        h_item = self._item_h(L)
        content_h = max(0, n_items * h_item)
        view_h = max(0, self._list_view_height(L))
        return max(0, content_h - view_h)

    def _clamp_scroll(self, L, n_items: int):
        self.scroll = max(0, min(self.scroll, self._max_scroll(L, n_items)))

    def _darken(self, rgb, factor=0.7):
        try:
            r, g, b = rgb
            return (max(0, int(r*factor)), max(0, int(g*factor)), max(0, int(b*factor)))
        except Exception:
            return rgb

    #  Helpers para soportar Contact 
    def _get(self, c, key, default=None):
        if isinstance(c, dict):
            return c.get(key, default)
        return getattr(c, key, default)

    #  Eventos 
    def handle_event(self, e, L, contacts: list[Contact]):
        """
        Devuelve:
          - MAC seleccionada (str),
          - "__ALL__" si se pulsa el botón 'Enviar a todos' (solo mensajes),
          - None si no hay cambio.
        """
        r = L["sidebar"]; pad = L["pad"]
        item_h = self._item_h(L)
        start_y = self._list_start_y(L)
        n = len(contacts)

        if e.type == pg.MOUSEWHEEL:
            self.scroll -= e.y * (item_h // 2)
            self._clamp_scroll(L, n)
            return None

        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
            if r.collidepoint(e.pos):
                mx, my = e.pos

                # Botón inferior: Enviar a todos
                btn_h = int(50 * L["s"])
                btn_rect = pg.Rect(r.x + pad, r.bottom - pad - btn_h, r.w - 2*pad, btn_h)
                if btn_rect.collidepoint(mx, my):
                    return "__ALL__"

                # Selección de fila
                if my >= start_y and my < btn_rect.top - pad:
                    y_rel = (my - start_y) + self.scroll
                    idx = y_rel // item_h
                    if 0 <= idx < n:
                        self.selected = idx
                        return self._get(contacts[idx], "mac", None)
            return None

        if e.type == pg.KEYDOWN and n > 0:
            cur = max(0, min(self.selected, n - 1))
            if e.key in (pg.K_UP, pg.K_k):
                new = max(0, cur - 1)
            elif e.key in (pg.K_DOWN, pg.K_j):
                new = min(n - 1, cur + 1)
            else:
                return None

            if new != cur:
                self.selected = new
                top_needed = new * item_h
                bot_needed = top_needed + item_h
                if top_needed < self.scroll:
                    self.scroll = top_needed
                elif bot_needed > self.scroll + self._list_view_height(L):
                    self.scroll = bot_needed - self._list_view_height(L)
                self._clamp_scroll(L, n)
                return self._get(contacts[new], "mac", None)

        return None

    #  Dibujo 
    def draw(self, surf, L, contacts):
        r = L["sidebar"]; pad = L["pad"]; f = L["fonts"]
        rounded_rect(surf, r, CLR["sidebar"], 0)

        # Encabezado
        title_y = r.y + L["pad"]
        icon_h = max(18, int(f["h2"].get_linesize() * 0.9))
        icon_w = icon_h

        text_pos = (r.x + pad, title_y)
        text(surf, "EnRedate", f["h2"], CLR["text"], text_pos)

        text_w = f["h2"].size("EnRedate")[0] if hasattr(f["h2"], "size") else 0
        if self._icon_brand:
            brand_icon = pg.transform.smoothscale(self._icon_brand, (icon_w, icon_h))
            surf.blit(brand_icon, (r.x + pad + text_w + 8, title_y))

        # Buscador
        search_r = self._search_rect(L)
        rounded_rect(surf, search_r, CLR["accent"], L["r_sm"])
        text(surf, "Buscar contactos...", f["p"], CLR["muted"],
             (search_r.x+12, search_r.y+search_r.h/2), "midleft")

        # Lista
        list_clip_prev = surf.get_clip()
        surf.set_clip(r)

        y = self._list_start_y(L) - self.scroll
        item_h = self._item_h(L)

        for idx, c in enumerate(contacts):
            row = pg.Rect(r.x, y, r.w, item_h)

            if idx == self.selected:
                sel = row.inflate(-4, -4)
                rounded_rect(surf, sel, CLR.get("sidebar_sel", CLR["accent"]), L["r_sm"])

            divider(surf, row.x+pad, row.bottom-1, row.right-pad)

            # Avatar circular 
            av_r = pg.Rect(r.x+pad, row.y+pad, int(42*L["s"]), int(42*L["s"]))
            pg.draw.circle(surf, CLR["accent"], av_r.center, av_r.w//2)

            if self._icon_user:
                icon_size = int(av_r.w * 0.75)
                icon = pg.transform.smoothscale(self._icon_user, (icon_size, icon_size))
                icon_pos = (av_r.centerx - icon_size//2, av_r.centery - icon_size//2)
                surf.blit(icon, icon_pos)

            if self._get(c, "online", False):
                dot(surf, (av_r.right-4, av_r.bottom-4), max(4, int(6*L["s"])), CLR["online"])

            name = self._get(c, "name", "?")
            msg  = self._get(c, "msg", "")
            tim  = self._get(c, "time", "")

            text(surf, name, f["h3"], CLR["text"], (av_r.right+10, av_r.y))
            text(surf, msg,  f["p"],  CLR["muted"], (av_r.right+10, av_r.y+f["h3"].get_linesize()+2))
            text(surf, tim,  f["xs"], CLR["muted"], (row.right-pad, av_r.y), "topright")

            y += item_h

        surf.set_clip(list_clip_prev)

        # Botón inferior —> Enviar a todos
        btn_h = int(50 * L["s"])
        btn = pg.Rect(r.x+pad, r.bottom-pad-btn_h, r.w-2*pad, btn_h)

        base_primary = CLR.get("primary", (40, 105, 255))
        btn_bg = CLR.get("primary_dark", self._darken(base_primary, 0.8)) 
        btn_fg = CLR.get("on_primary", (255, 255, 255))

        rounded_rect(surf, btn, btn_bg, L["r_sm"])

        label = "Enviar a todos"
        font_btn = f["btn"]
        text_w = font_btn.size(label)[0] if hasattr(font_btn, "size") else 0
        gap = int(10 * L["s"])
        icon_size = max(18, int(btn_h * 0.6))
        total_w = icon_size + gap + text_w

        start_x = int(btn.centerx - total_w / 2)
        icon_y = int(btn.y + (btn_h - icon_size) / 2)
        text_x = start_x + icon_size + gap
        text_y = btn.centery

        if self._icon_all:
            icon_scaled = pg.transform.smoothscale(self._icon_all, (icon_size, icon_size))
            surf.blit(icon_scaled, (start_x, icon_y))

        text(surf, label, font_btn, btn_fg, (text_x, text_y), "midleft")
