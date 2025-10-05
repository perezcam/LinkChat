import pygame as pg
from core.theme import CLR

def rounded_rect(surf, rect, color, radius):
    pg.draw.rect(surf, color, rect, border_radius=radius)

def text(surf, s, font, color, pos, anchor="topleft"):
    img = font.render(s, True, color)
    r = img.get_rect(**{anchor: pos})
    surf.blit(img, r)
    return r

def dot(surf, center, r, color):
    pg.draw.circle(surf, color, center, r)

def divider(surf, x1, y, x2):
    pg.draw.line(surf, CLR["border"], (x1, y), (x2, y), 1)
