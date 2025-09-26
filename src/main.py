import logging
import signal
import sys
import time
from contextlib import suppress

# Importa las implementaciones del proyecto (rutas según tu estructura)
from src.core.managers.raw_socket import SocketManager          # crea el socket y fija .mac
from src.core.managers.service_threads import ThreadManager     # hilos: receiver/sender/dispatcher/scheduler
from src.core.discover import Discovery                         # discovery que usa ThreadManager

# EtherType que estás usando en el proyecto
ETHER_TYPE = 0x88B5

# Configuración mínima de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def main():
    INTERFACE = "eth0"          # <- cambia por la interfaz real que usarás en la máquina / contenedor
    ALIAS = "Nodo-Camilo"       # <- alias que quieres anunciar

    # Señal para parada limpia
    stop_requested = False

    def _on_sigint(signum, frame):
        nonlocal stop_requested
        logging.info("Señal de terminación recibida. Iniciando cierre ordenado...")
        stop_requested = True

    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigint)

    # 1) Abrir el SocketManager usando context manager (asegura que .mac quede disponible)
    try:
        with SocketManager(interface=INTERFACE, ethertype=ETHER_TYPE) as sock:
            # Ahora sock.mac ya está establecido (get_mac/getsockname ya fue consultado)
            logging.info(f"MAC local detectada: {sock.mac}")

            # 2) Crear y arrancar ThreadManager (usa el socket ya abierto)
            thmgr = ThreadManager(socket_manager=sock)

            # (Opcional) si quieres registrar handlers adicionales: thmgr.message_handlers[...]=fn

            thmgr.start()
            logging.info("ThreadManager arrancado (receiver/sender/dispatcher/scheduler).")

            # 3) Crear Discovery, adjuntarlo y arrancar su tarea periódica
            discover = Discovery(service_threads=thmgr, alias=ALIAS, interval_seconds=5.0)
            # attach registra handlers y añade la tarea periódica a ThreadManager
            discover.attach()
            logging.info("Discovery adjuntado y timer programado.")

            # callback opcional para visualización cuando cambie la tabla de vecinos
            def on_neighbors_changed(neighs):
                resumen = [{ "mac": mac, "alias": v["alias"] } for mac, v in neighs.items()]
                logging.info(f"[app] vecinos = {resumen}")

            discover.set_on_neighbors_changed(on_neighbors_changed)

            # Bucle principal: se queda hasta que pidamos parar
            try:
                while not stop_requested:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                stop_requested = True

            # ------- Cierre ordenado -------
            logging.info("Parando ThreadManager...")
            thmgr.stop()
            # ThreadManager.stop() usa shutdown_event y hace join() a los hilos

            # Si Discovery necesitara detach (no obligatorio), lo hacemos:
            with suppress(Exception):
                discover.detach()

            logging.info("Aplicación finalizada limpiamente.")

    except PermissionError:
        logging.error("No tienes permisos para abrir raw sockets. Ejecuta con sudo o ajusta capacidades del contenedor.")
        sys.exit(1)
    except OSError as e:
        logging.error(f"Error al abrir el socket: {e}")
        sys.exit(1)
    except Exception as e:
        logging.exception(f"Error inesperado en main: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
