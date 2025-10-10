import os
import stat
import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

def _resolve_socket_path() -> str:
    alias = os.environ.get("NODE_ALIAS", "Nodo-A").strip()
    print("conectado a",alias)
    return os.environ.get("IPC_SOCKET", f"/ipc/linkchat-{alias}.sock")

class IPCServer:
    """
    Servidor IPC por Unix Domain Socket (UDS) con protocolo NDJSON (una línea JSON por mensaje).

    on_cmd: async function(dict) -> dict|None
      - Recibe un comando como diccionario.
      - Devuelve dict (se responde al cliente) o None (no se responde).
    """

    def __init__(self, on_cmd: Callable[[dict], Awaitable[Optional[dict]]], socket_path: Optional[str] = None):
        self.on_cmd = on_cmd
        self.socket_path = socket_path or _resolve_socket_path()
        self._writers = set()
        self._server: Optional[asyncio.AbstractServer] = None
        self._stopping = asyncio.Event()

    async def start(self):
        # Asegurar el directorio
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)

        try:
            st = os.lstat(self.socket_path)
            if stat.S_ISSOCK(st.st_mode):
                os.unlink(self.socket_path)
            else:
                raise RuntimeError(f"[IPC] La ruta {self.socket_path} existe y NO es un socket.")
        except FileNotFoundError:
            pass

        # Crear el servidor UDS
        self._server = await asyncio.start_unix_server(self._handle_client, path=self.socket_path, backlog=128)

      
        try:
            os.chmod(self.socket_path, 0o666)
        except Exception as e:
            logging.warning(f"[IPC] No se pudieron ajustar permisos del socket: {e}")

        logging.info(f"[IPC] Escuchando en {self.socket_path}")

        # Servir hasta que se pida stop()
        async with self._server:
            await self._stopping.wait()

    async def stop(self):
        # Detiene aceptaciones y cierra clientes
        self._stopping.set()
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None

        # Cerrar writers conectados
        for w in list(self._writers):
            try:
                w.close()
                await w.wait_closed()
            except Exception:
                pass
        self._writers.clear()

        # Limpiar el archivo del socket
        try:
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
        except Exception as e:
            logging.warning(f"[IPC] No se pudo eliminar el socket en stop(): {e}")

        logging.info("[IPC] Servidor detenido y socket limpiado.")

    async def broadcast(self, payload: dict):
        """Envía un JSON a todos los clientes conectados (terminado en \\n)."""
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        to_drop = []
        for w in list(self._writers):
            try:
                w.write(data)
                await w.drain()
            except Exception:
                to_drop.append(w)
        for w in to_drop:
            self._writers.discard(w)
            try:
                w.close()
                await w.wait_closed()
            except Exception:
                pass

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        # Registrar cliente
        self._writers.add(writer)
        peer = None

        try:
            # En UDS, get_extra_info("peername") puede ser None o vacío
            peer = writer.get_extra_info("peername")
            logging.debug(f"[IPC] Cliente conectado: {peer}")

            while True:
                # Límite de mensaje: evita lecturas infinitas si el cliente nunca manda '\n'
                line = await reader.readline()
                if not line:
                    break

                try:
                    cmd = json.loads(line.decode("utf-8"))
                    if not isinstance(cmd, dict):
                        raise ValueError("El comando debe ser un objeto JSON")
                except Exception as e:
                    logging.exception(f"[IPC] JSON inválido: {e}")
                    err = {"ok": False, "error": "bad_json"}
                    writer.write((json.dumps(err) + "\n").encode("utf-8"))
                    await writer.drain()
                    continue

                try:
                    resp = await self.on_cmd(cmd)
                    if resp is not None:
                        writer.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
                        await writer.drain()
                except Exception as e:
                    logging.exception(f"[IPC] Error en on_cmd: {e}")
                    err = {"ok": False, "error": "server_exception"}
                    writer.write((json.dumps(err) + "\n").encode("utf-8"))
                    await writer.drain()

        finally:
            # Desregistrar
            self._writers.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logging.debug(f"[IPC] Cliente desconectado: {peer}")
