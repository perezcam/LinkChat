import pygame as pg
from core.theme import CLR
from core.draw import rounded_rect, text, dot, divider

class ChatHeader:
    def draw(self, surf, L, contact_name="Contacto", online=False):
        r = L["header"]; pad = L["pad"]; f = L["fonts"]
        rounded_rect(surf, r, CLR["bg"], 0)
        divider(surf, r.x, r.bottom-1, r.right)

        av = pg.Rect(r.x+pad, r.y+pad, int(40*L["s"]), int(40*L["s"]))
        pg.draw.circle(surf, CLR["accent"], av.center, av.w//2)
        if online:
            dot(surf, (av.right, av.bottom), max(5, int(6*L["s"])), CLR["online"])
        text(surf, contact_name, f["h3"], CLR["text"], (av.right+10, av.y))
        text(surf, "Online" if online else "Offline", f["xs"], CLR["muted"], (av.right+10, av.y+f["h3"].get_linesize()+2))
