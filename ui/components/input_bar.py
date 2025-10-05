import pygame as pg
from core.theme import CLR
from core.draw import rounded_rect, text, divider

class InputBar:
    def __init__(self):
        self.buffer = ""

    def handle_event(self, e):
        if e.type == pg.KEYDOWN:
            if e.key == pg.K_BACKSPACE:
                self.buffer = self.buffer[:-1]
            elif e.key == pg.K_RETURN and (pg.key.get_mods() & pg.KMOD_SHIFT) == 0:
                msg = self.buffer.strip()
                self.buffer = ""
                return msg
            else:
                if e.unicode and e.key != pg.K_RETURN:
                    self.buffer += e.unicode
        return None

    def draw(self, surf, L):
        r = L["input"]; pad = L["pad"]; f = L["fonts"]
        rounded_rect(surf, r, CLR["bg"], 0)
        divider(surf, r.x, r.y, r.right)

        av = pg.Rect(r.x+pad, r.y+pad, int(54*L["s"]), int(54*L["s"]))
        pg.draw.circle(surf, CLR["accent"], av.center, av.w//2)

        tx = pg.Rect(av.right + pad, r.y+pad, r.w - (av.w + pad*4 + int(50*L["s"]) + int(50*L["s"])), av.h)
        rounded_rect(surf, tx, CLR["accent"], L["r_sm"])
        text(surf, self.buffer or "Type a message...", f["p"], CLR["muted"], (tx.x+12, tx.centery), "midleft")

        b1 = pg.Rect(tx.right + pad, tx.y, int(50*L["s"]), tx.h)
        rounded_rect(surf, b1, CLR["button"], L["r_sm"])
        text(surf, "📎", f["h3"], CLR["primary_fg"], b1.center, "center")

        b2 = pg.Rect(b1.right + pad, tx.y, int(50*L["s"]), tx.h)
        rounded_rect(surf, b2, CLR["button"], L["r_sm"])
        text(surf, "➤", f["h3"], CLR["primary_fg"], b2.center, "center")
