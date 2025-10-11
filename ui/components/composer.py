import os
import pygame as pg
from core.theme import CLR
from core.draw import rounded_rect, text

class FileChip:
    def __init__(self, path: str, icon_surf: pg.Surface):
        self.path = path
        self.name = os.path.basename(path)
        self.icon = icon_surf
        self.rect = pg.Rect(0, 0, 0, 0)
        self.close_rect = pg.Rect(0, 0, 0, 0)
        self._display_name = self.name

class Composer:
    """
    Orquesta:
      - chips de adjuntos sobre la barra
      - input_bar (existente)

    API:
      - set_broadcast_mode(bool)   # <- NUEVO
      - handle_event(e) -> ("attach", None) | ("send", {"text":str,"files":[str,...]}) | None
      - draw(surf, L)
      - add_files(list[str])
      - clear_files()
      - get_files() -> list[str]

    Reglas:
      - En broadcast: SOLO texto (sin adjuntos).
      - No se puede enviar mensaje vacío (sin texto y sin archivos).
      - Sí se puede enviar solo archivos (texto vacío) cuando NO es broadcast.
    """
    def __init__(self, input_bar, images_dir="images"):
        self.input_bar = input_bar
        self._files: list[FileChip] = []

        # Ícono del archivo (como en InputBar: cargamos desde images/*.svg)
        p = os.path.join(images_dir, "file.svg")
        try:
            self._file_icon = pg.image.load(p).convert_alpha()
        except Exception:
            # Fallback mínimo si falta el SVG
            surf = pg.Surface((24, 24), pg.SRCALPHA)
            pg.draw.rect(surf, CLR["muted"], surf.get_rect(), border_radius=4)
            self._file_icon = surf

        self._r = None
        self._r_chips = None

        # --- NUEVO: flag de broadcast ---
        self.broadcast_mode: bool = False

    # ---------------- broadcast ----------------
    def set_broadcast_mode(self, on: bool):
        """Activa/desactiva modo broadcast (solo texto). Limpia chips al activarse."""
        on = bool(on)
        if on and self._files:
            self.clear_files()
        self.broadcast_mode = on
        # Placeholder opcional
        if hasattr(self.input_bar, "set_placeholder"):
            self.input_bar.set_placeholder("Mensaje a todos…" if on else "Escribe un mensaje…")

    # ---------------- files ----------------
    def add_files(self, paths: list[str]):
        # En broadcast no aceptamos adjuntos
        if self.broadcast_mode:
            return
        for p in paths:
            self._files.append(FileChip(p, self._file_icon))

    def clear_files(self):
        self._files.clear()

    def get_files(self) -> list[str]:
        return [c.path for c in self._files]

    # ---------------- layout ----------------
    def _compute_rects(self, L):
        # Asegura que InputBar compute primero sus rects
        self.input_bar._compute_rects(L)
        r_bar = self.input_bar._r

        pad = L["pad"]
        s = L["s"]
        chip_h = int(36 * s)

        # Fila donde dibujamos chips (encima de la barra)
        # Si es broadcast, no hay zona de chips.
        if self.broadcast_mode:
            self._r_chips = None
        else:
            self._r_chips = pg.Rect(r_bar.x, r_bar.y - pad - chip_h, r_bar.w, chip_h)

        self._r = r_bar

        if self.broadcast_mode or not self._r_chips:
            return

        # Posicionar cada chip
        x = self._r_chips.x + pad
        y = self._r_chips.y + (self._r_chips.h - chip_h) // 2
        font = L["fonts"]["p"]
        maxw = int(220 * s)

        for c in self._files:
            # Truncado del nombre para que quepa en el chip
            name = c.name
            while font.size(name)[0] > maxw - (chip_h + 12 + 20) and len(name) > 6:
                name = name[:-2] + "…"
            c._display_name = name

            w = min(maxw, chip_h + 12 + font.size(name)[0] + 20)
            c.rect = pg.Rect(x, y, w, chip_h)
            c.close_rect = pg.Rect(
                c.rect.right - 22,
                c.rect.y + (chip_h - 18) // 2,
                18, 18
            )
            x += w + 8

    # --------------- eventos ----------------
    def handle_event(self, e):
        # Gestiona clic para cerrar chips (solo si hay zona de chips activa)
        if not self.broadcast_mode and e.type == pg.MOUSEBUTTONDOWN and e.button == 1 and self._r_chips:
            if self._r_chips.collidepoint(e.pos):
                for idx, c in enumerate(list(self._files)):
                    if c.close_rect.collidepoint(e.pos):
                        self._files.pop(idx)
                        return None

        # Delegamos a la barra (adjuntar / enviar / escribir)
        out = self.input_bar.handle_event(e)
        if not out:
            return None

        kind, payload = out

        if kind == "attach":
            # En broadcast ignoramos completamente el attach
            if self.broadcast_mode:
                return None
            return ("attach", None)

        if kind == "send":
            txt = (payload or "").strip()
            files = self.get_files()

            # En broadcast: debe haber texto (no adjuntos)
            if self.broadcast_mode:
                if not txt:
                    return None
                self.input_bar.value = ""
                return ("send", {"text": txt, "files": []})

            # No broadcast: permitir solo archivos o texto+archivos
            if not txt and not files:
                return None

            # Limpiar input y chips SOLO si realmente se envía
            self.input_bar.value = ""
            data = {"text": txt, "files": files}
            self.clear_files()
            return ("send", data)

        return None

    # --------------- dibujo -----------------
    def draw(self, surf, L):
        self._compute_rects(L)

        # Capa de chips (solo si NO es broadcast y hay archivos)
        if (not self.broadcast_mode) and self._files and self._r_chips:
            rounded_rect(surf, self._r_chips, CLR["panel"], L["r_sm"])
            for c in self._files:
                # Chip
                rounded_rect(surf, c.rect, CLR["surface_alt"], L["r_sm"])

                # Icono escalado al alto del chip
                icon_size = c.rect.h - 10
                if icon_size > 0:
                    icon = pg.transform.smoothscale(c.icon, (icon_size, icon_size))
                    surf.blit(icon, (c.rect.x + 6, c.rect.y + 5))

                # Texto
                text(
                    surf, c._display_name, L["fonts"]["p"], CLR["text"],
                    (c.rect.x + 12 + icon_size, c.rect.centery), "midleft"
                )

                # Botón cerrar
                pg.draw.circle(surf, CLR["accent"], c.close_rect.center, c.close_rect.w // 2)
                text(surf, "×", L["fonts"]["p"], CLR["text"], c.close_rect.center, "center")

        # Barra de entrada
        self.input_bar.draw(surf, L)
