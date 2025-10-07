import pygame as pg
from core.theme import CLR
from core.draw import rounded_rect, text, divider, dot
from state.models import Contact

class Sidebar:
    def __init__(self):
        self.selected = 0   
        self.scroll = 0   

    # ----------------- Helpers internos -----------------
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
        # Alto visible real para la lista (excluye el botón inferior y márgenes)
        r = L["sidebar"]; pad = L["pad"]
        btn_h = int(50 * L["s"])
        return r.h - ((self._list_start_y(L) - r.y) + pad + btn_h)

    def _max_scroll(self, L, n_items: int) -> int:
        # Contenido total menos ventana visible (no negativo)
        h_item = self._item_h(L)
        content_h = max(0, n_items * h_item)
        view_h = max(0, self._list_view_height(L))
        return max(0, content_h - view_h)

    def _clamp_scroll(self, L, n_items: int):
        self.scroll = max(0, min(self.scroll, self._max_scroll(L, n_items)))

    # ----------------- Eventos -----------------
    def handle_event(self, e, L, contacts:list[Contact]):
        """
        e: evento de pygame
        L: layout (usa L["sidebar"], L["pad"], L["fonts"], L["s"])
        contacts: lista de dicts: {"mac", "name", "online", "msg", "time"}
        Devuelve la mac seleccionada o None si no cambia selección.
        """
        r = L["sidebar"]; pad = L["pad"]
        item_h = self._item_h(L)
        start_y = self._list_start_y(L)
        n = len(contacts)

        # Scroll con rueda
        if e.type == pg.MOUSEWHEEL:
            # pygame: e.y > 0 rueda arriba → desplazar hacia arriba 
            self.scroll -= e.y * (item_h // 2)
            self._clamp_scroll(L, n)
            return None

        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
            if r.collidepoint(e.pos):
                mx, my = e.pos

                # Evitar que el botón inferior capture selección de la lista
                btn_h = int(50 * L["s"])
                btn_rect = pg.Rect(r.x + pad, r.bottom - pad - btn_h, r.w - 2*pad, btn_h)
                if btn_rect.collidepoint(mx, my):
                    return None

                if my >= start_y and my < btn_rect.top - pad:
                    y_rel = (my - start_y) + self.scroll
                    idx = y_rel // item_h
                    if 0 <= idx < n:
                        self.selected = idx
                        mac = contacts[idx].mac
                        return mac
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
                return contacts[new].mac

        return None

    # ----------------- Dibujo -----------------
    def draw(self, surf, L, contacts):
        r = L["sidebar"]; pad = L["pad"]; f = L["fonts"]
        rounded_rect(surf, r, CLR["sidebar"], 0)
        text(surf, "EnRedate", f["h2"], CLR["text"], (r.x+pad, r.y+pad))

        search_r = self._search_rect(L)
        rounded_rect(surf, search_r, CLR["accent"], L["r_sm"])
        text(surf, "Buscar contactos...", f["p"], CLR["muted"], (search_r.x+12, search_r.y+search_r.h/2), "midleft")

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

            av_r = pg.Rect(row.x+pad, row.y+pad, int(42*L["s"]), int(42*L["s"]))
            pg.draw.circle(surf, CLR["accent"], av_r.center, av_r.w//2)

            if c.get("online"):
                dot(surf, (av_r.right-4, av_r.bottom-4), max(4, int(6*L["s"])), CLR["online"])

            text(surf, c.get("name","?"), f["h3"], CLR["text"], (av_r.right+10, av_r.y))
            text(surf, c.get("msg",""),  f["p"],  CLR["muted"], (av_r.right+10, av_r.y+f["h3"].get_linesize()+2))
            text(surf, c.get("time",""), f["xs"], CLR["muted"], (row.right-pad, av_r.y), "topright")

            y += item_h

        surf.set_clip(list_clip_prev)

        btn_h = int(50*L["s"])
        btn = pg.Rect(r.x+pad, r.bottom-pad-btn_h, r.w-2*pad, btn_h)
        rounded_rect(surf, btn, CLR["text"], L["r_sm"])
        text(surf, "Nuevo Mensaje", f["btn"], CLR["primary_fg"], btn.center, "center")
