from typing import Callable, Optional

_sink_started: Optional[Callable[[dict], None]] = None
_sink_progress: Optional[Callable[[dict], None]] = None
_sink_finished: Optional[Callable[[dict], None]] = None
_sink_error: Optional[Callable[[dict], None]] = None


def set_sinks(*,
              on_started: Callable[[dict], None] | None = None,
              on_progress: Callable[[dict], None] | None = None,
              on_finished: Callable[[dict], None] | None = None,
              on_error: Callable[[dict], None] | None = None):
    """Registra callbacks para redirigir los eventos a UI."""
    global _sink_started, _sink_progress, _sink_finished, _sink_error
    _sink_started = on_started
    _sink_progress = on_progress
    _sink_finished = on_finished
    _sink_error = on_error


def emit_started(*, file_id: str, src: str, name: str, rel: str | None):
    if _sink_started:
        try:
            _sink_started({"file_id": file_id, "src": src, "name": name, "rel": rel})
        except Exception:
            pass


def emit_progress(*, file_id: str, src: str, name: str, rel: str | None,
                  acked: int, total: int, progress: float):
    if _sink_progress:
        try:
            _sink_progress({
                "file_id": file_id, "src": src, "name": name, "rel": rel,
                "acked": acked, "total": total, "progress": progress
            })
        except Exception:
            pass


def emit_finished(*, file_id: str, src: str, name: str, rel: str | None, status: str):
    if _sink_finished:
        try:
            _sink_finished({"file_id": file_id, "src": src, "name": name, "rel": rel, "status": status})
        except Exception:
            pass


def emit_error(*, file_id: str, src: str | None, name: str | None, rel: str | None, error: str):
    if _sink_error:
        try:
            _sink_error({"file_id": file_id, "src": src, "name": name, "rel": rel, "error": error})
        except Exception:
            pass
