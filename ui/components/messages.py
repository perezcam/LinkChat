from core.theme import CLR
from core.draw import rounded_rect, text
import pygame as pg

class MessagesView:
    def __init__(self):
        self.wrap_cache = {}

    def _wrap(self, font, body, maxw):
        key = (id(font), body, maxw)
        cached = self.wrap_cache.get(key)
        if cached: return cached
        words = body.split(" ")
        lines, cur = [], ""
        for w_ in words:
            test = (cur + " " + w_).strip()
            if font.size(test)[0] <= maxw:
                cur = test
            else:
                if cur: lines.append(cur)
                cur = w_
        if cur: lines.append(cur)
        self.wrap_cache[key] = lines
        return lines

    def draw(self, surf, L, messages):
        r = L["messages"]; pad = L["pad"]; f = L["fonts"]
        x_left  = r.x + pad*2
        x_right = r.right - pad*2
        y = r.y + pad
        for m in messages:
            is_tx = (m.get("side") == "tx")
            body = m.get("text","")
            font = f["p"]
            maxw = min(L["bubble_max"], r.w * 0.48)
            lines = self._wrap(font, body, maxw)

            text_w = max(font.size(line)[0] for line in lines) if lines else 0
            text_h = len(lines) * font.get_linesize()
            pad_bub = int(12 * L["s"])
            bw, bh = text_w + pad_bub*2, text_h + pad_bub*2 + font.get_linesize()

            if is_tx:
                bx = x_right - bw
                color = CLR["primary"]; fg = CLR["primary_fg"]
            else:
                bx = x_left
                color = CLR["bubble_rx"]; fg = CLR["text"]

            br = pg.Rect(int(bx), int(y), int(bw), int(bh))
            rounded_rect(surf, br, color, L["r_lg"])

            ty = br.y + pad_bub
            for line in lines:
                text(surf, line, font, fg, (br.x + pad_bub, ty))
                ty += font.get_linesize()

            ts_color = (fg if is_tx else (113,113,130))
            text(surf, m.get("time",""), f["xs"], ts_color, (br.x + pad_bub, br.bottom - pad_bub))

            y = br.bottom + int(16 * L["s"])
