import os
import pygame as pg
from core.theme import CLR
from core.draw import rounded_rect, text, dot, divider

class ChatHeader:
    def __init__(self, images_dir: str = "images"):
        self._icon_user = None
        p_user = os.path.join(images_dir, "user.svg")
        try:
            self._icon_user = pg.image.load(p_user).convert_alpha()
        except Exception:
            # Fallback: sin icono, solo quedará el círculo
            self._icon_user = None

    def draw(self, surf, L, contact_name="Contacto", online=False):
        r = L["header"]; pad = L["pad"]; f = L["fonts"]

        rounded_rect(surf, r, CLR["bg"], 0)
        divider(surf, r.x, r.bottom-1, r.right)

        # Avatar circular
        av = pg.Rect(r.x + pad, r.y + pad, int(40 * L["s"]), int(40 * L["s"]))
        pg.draw.circle(surf, CLR["accent"], av.center, av.w // 2)

        # Icono user centrado dentro del avatar
        if self._icon_user:
            icon_size = max(16, int(av.w * 0.72))  
            icon = pg.transform.smoothscale(self._icon_user, (icon_size, icon_size))
            surf.blit(icon, (av.centerx - icon_size // 2, av.centery - icon_size // 2))

        # Estado online 
        if online:
            br = (av.right - 4, av.bottom - 4)  
            dot(surf, br, max(5, int(6 * L["s"])), CLR["online"])

        text(surf, contact_name, f["h3"], CLR["text"], (av.right + 10, av.y))
        subtitle = "Online" if online else "Offline"
        text(surf, subtitle, f["xs"], CLR["muted"], (av.right + 10, av.y + f["h3"].get_linesize() + 2))
