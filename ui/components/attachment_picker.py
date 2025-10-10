import pygame as pg
import pygame_gui

class AttachmentPicker:
    def __init__(self,
                 manager: pygame_gui.UIManager,
                 size_ratio: tuple[float, float] = (0.9, 0.9),
                 allow_dirs: bool = True,
                 title: str = "Adjuntar"):
        self.manager = manager
        self.size_ratio = size_ratio
        self.allow_dirs = allow_dirs
        self.title = title
        self.dialog: pygame_gui.windows.UIFileDialog | None = None
        self.attachments: list[str] = []
        self._last_mgr_size: tuple[int, int] | None = None

    # --- helpers ---
    def _mgr_size(self) -> tuple[int, int]:
        try:
            return self.manager.get_window_resolution()
        except Exception:
            surf = pg.display.get_surface()
            return surf.get_size() if surf else (1280, 720)

    def _apply_modal_fixed(self):
        if not self.dialog:
            return
        # modal
        try:
            self.dialog.set_blocking(True)
        except Exception:
            pass
        # no movible
        try:
            self.dialog.draggable = False
        except Exception:
            pass

    def _recenter_and_resize(self):
        if not self.dialog:
            return
        w, h = self._mgr_size()
        ww = max(480, int(w * self.size_ratio[0]))
        hh = max(360, int(h * self.size_ratio[1]))
        # primero dimensiona, luego centra
        try:
            self.dialog.set_dimensions((ww, hh))
        except Exception:
            pass
        # centra relativo al viewport actual del UIManager
        try:
            self.dialog.center_window()
        except Exception:
            # fallback manual por si tu versión no trae center_window()
            x = (w - ww) // 2
            y = (h - hh) // 2
            try:
                self.dialog.set_position((x, y))
            except Exception:
                pass
        self._apply_modal_fixed()

    # --- API ---
    def open(self):
        if self.dialog is not None:
            self._recenter_and_resize()
            return
        # crea con un rect provisional; se ajusta justo después
        w, h = self._mgr_size()
        tmp = pg.Rect(0, 0, int(w * 0.5), int(h * 0.5))
        self.dialog = pygame_gui.windows.UIFileDialog(
            rect=tmp,
            manager=self.manager,
            window_title=self.title,
            allow_picking_directories=self.allow_dirs,
            allow_existing_files_only=True
        )
        self._recenter_and_resize()
        self._last_mgr_size = self._mgr_size()

    def is_open(self) -> bool:
        return self.dialog is not None

    def process_event(self, event: pg.event.Event):
        if self.dialog is None:
            return

        if event.type == pg.USEREVENT:
            if event.user_type == pygame_gui.UI_FILE_DIALOG_PATH_PICKED:
                path = event.text
                if path:
                    self.attachments.append(path)
                self.dialog.kill()
                self.dialog = None
            elif event.user_type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element == self.dialog:
                self.dialog.kill()
                self.dialog = None

        elif event.type in (pg.VIDEORESIZE, pg.WINDOWSIZECHANGED, pg.WINDOWRESIZED):
            # cuando cambia el tamaño de la ventana, re-centra y redimensiona
            self._recenter_and_resize()
            self._last_mgr_size = self._mgr_size()

    def update(self, dt: float):
        """Llamar cada frame. Si cambió la resolución, re-centra."""
        if self.dialog is None:
            return
        cur = self._mgr_size()
        if self._last_mgr_size != cur:
            self._recenter_and_resize()
            self._last_mgr_size = cur

    def take_attachments(self) -> list[str]:
        out = self.attachments[:]
        self.attachments.clear()
        return out
