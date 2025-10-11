import contextlib
import asyncio
import json
import logging
import queue
from typing import Optional


class UDSBridge:
    """
    Puente IPC sobre Unix Domain Socket.
    - start(): conecta (con backoff) y lanza el reader loop.
    - poll_event(): obtiene eventos (dict) sin bloquear desde una cola interna.
    - send_cmd(cmd): (async) envía un comando JSONL (no espera respuesta RPC).
    - send_cmd_threadsafe(cmd): dispara send_cmd desde cualquier hilo (Pygame).
    - stop(): cierra lector y conexión limpiamente.
    """

    def __init__(self, socket_path: str = "/ipc/linkchat-Nodo-A.sock"):
        self.socket_path = socket_path
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._evq: "queue.Queue[dict]" = queue.Queue()
        self._task: Optional[asyncio.Task] = None
        self._stopping: bool = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    #  lifecycle 
    async def start(self) -> None:
        """Conecta al UDS con backoff y lanza el bucle lector."""
        self.loop = asyncio.get_running_loop()

        delay = 0.2
        while not self._stopping:
            try:
                logging.info("[IPC] Conectando a %s ...", self.socket_path)
                self._reader, self._writer = await asyncio.open_unix_connection(self.socket_path)
                logging.info("[IPC] Conexión establecida con %s", self.socket_path)
                break
            except Exception as e:
                logging.debug("[IPC] Aún no disponible (%s). Reintentando en %.2fs", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 1.7, 2.0)

        if not self._reader or not self._writer:
            logging.warning("[IPC] No se pudo establecer la conexión a %s", self.socket_path)
            return

        self._task = asyncio.create_task(self._reader_loop(), name="ipc_reader_loop")

    async def _reader_loop(self) -> None:
        """Lee líneas JSONL del socket y las deposita en la cola de eventos."""
        logging.info("[IPC] readerLoop iniciado (socket_path=%s)", self.socket_path)
        try:
            while not self._stopping:
                line: bytes = await self._reader.readline()
                if not line:
                    logging.warning("[IPC] EOF recibido. Cerrando readerLoop.")
                    break
                try:
                    evt = json.loads(line.decode("utf-8", "replace"))
                except Exception:
                    logging.exception("[IPC] Línea inválida (no JSON). La descarto.")
                    continue
                self._evq.put(evt)
        except asyncio.CancelledError:
            pass
        except Exception:
            logging.exception("[IPC] Error en readerLoop")
        finally:
            await self._close_streams()
            logging.info("[IPC] readerLoop terminado.")

    #  API 
    async def send_cmd(self, cmd: dict) -> None:
        """
        Envía un comando (dict) como JSONL al backend.
        No espera respuesta RPC: las respuestas llegan por el mismo stream y
        el reader_loop las entrega via poll_event().
        """
        if not self._writer:
            logging.debug("[IPC] send_cmd ignorado: no hay writer.")
            return
        try:
            data = (json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8")
            self._writer.write(data)
            await self._writer.drain()
        except Exception:
            logging.exception("[IPC] Error enviando comando")

    def send_cmd_threadsafe(self, cmd: dict):
        """
        Variante thread-safe: agenda send_cmd en el loop del bridge.
        Retorna concurrent.futures.Future (resultado: None).
        """
        if not self.loop:
            raise RuntimeError("UDSBridge: start() no inicializado (loop=None)")
        return asyncio.run_coroutine_threadsafe(self.send_cmd(cmd), self.loop)

    # alias cómodo
    def post(self, cmd: dict):
        return self.send_cmd_threadsafe(cmd)

    def poll_event(self) -> Optional[dict]:
        """Devuelve un evento pendiente (si hay) sin bloquear."""
        try:
            return self._evq.get_nowait()
        except queue.Empty:
            return None

    async def stop(self) -> None:
        """Detiene el loop lector y cierra la conexión."""
        self._stopping = True
        if self._task:
            self._task.cancel()
            with contextlib.suppress(Exception):
                await self._task
        await self._close_streams()

    #  helpers 
    async def _close_streams(self) -> None:
        """Cierra writer y resetea referencias."""
        if self._writer:
            try:
                self._writer.close()
                with contextlib.suppress(Exception):
                    await self._writer.wait_closed()
            except Exception:
                logging.debug("[IPC] Error cerrando writer", exc_info=True)
        self._reader = None
        self._writer = None
