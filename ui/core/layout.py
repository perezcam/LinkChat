import pygame as pg

CAPTION = "EnRedaTe – UI"
BASE_W, BASE_H = 1280, 800

def init_window():
    pg.display.set_caption(CAPTION)
    return pg.display.set_mode((BASE_W, BASE_H), pg.RESIZABLE)

def make_fonts(scale: float):
    def F(px): return pg.font.SysFont("Inter,Arial,Helvetica", max(12, int(px * scale)), False, False)
    return {
        "h2": F(20), "h3": F(16), "p": F(15), "xs": F(12), "btn": F(15),
    }

def compute_layout(w, h):
    s = min(w / BASE_W, h / BASE_H)
    sidebar_w   = int(320 * s)
    header_h    = int(72  * s)
    input_h     = int(80  * s)
    pad         = int(16  * s)
    radius_lg   = int(16  * s)
    radius_sm   = int(10  * s)
    bubble_max  = int(520 * s)

    fonts = make_fonts(s)

    sidebar_r   = pg.Rect(0, 0, sidebar_w, h)
    chat_r      = pg.Rect(sidebar_w, 0, w - sidebar_w, h)
    header_r    = pg.Rect(chat_r.x, chat_r.y, chat_r.w, header_h)
    messages_r  = pg.Rect(chat_r.x, header_r.bottom, chat_r.w, h - header_h - input_h)
    input_r     = pg.Rect(chat_r.x, h - input_h, chat_r.w, input_h)

    return {
        "s": s, "fonts": fonts, "pad": pad, "r_lg": radius_lg, "r_sm": radius_sm,
        "bubble_max": bubble_max,
        "sidebar": sidebar_r, "chat": chat_r, "header": header_r,
        "messages": messages_r, "input": input_r
    }
