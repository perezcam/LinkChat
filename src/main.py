# src/main.py
import os
import sys
import time
import signal
import argparse
import logging

from src.core.managers.raw_socket import SocketManager
from src.core.managers.service_threads import ThreadManager
from src.file_transfer.handlers.file_transfer_handler import FileTransferHandler

# Estos dos módulos deben existir según tu estructura actual:
from src.file_transfer.file_sender import FileSender
from src.file_transfer.file_receiver import FileReceiver

# --------------------------------------------------------------------------------------
# Utilidad: leer INTERFACE y ETHER_TYPE desde env o defaults (alineado con docker-compose)
# --------------------------------------------------------------------------------------
def read_net_env():
    interface = os.environ.get("INTERFACE", "eth0")
    ether_type_str = os.environ.get("ETHER_TYPE", "0x88B5")
    try:
        ether_type = int(ether_type_str, 16)
    except ValueError:
        raise RuntimeError(f"ETHER_TYPE inválido: {ether_type_str}")
    return interface, ether_type

# --------------------------------------------------------------------------------------
# Señales para apagado limpio
# --------------------------------------------------------------------------------------
_shutdown = False
def _handle_sig(*_):
    global _shutdown
    _shutdown = True

for _sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(_sig, _handle_sig)

# --------------------------------------------------------------------------------------
# Modo receptor (server)
# --------------------------------------------------------------------------------------
def run_recv(base_dir: str | None):
    interface, ether_type = read_net_env()
    logging.info(f"[recv] Iniciando receptor en IF={interface} EtherType={hex(ether_type)} base_dir={base_dir or '(default)'}")

    with SocketManager(interface=interface, ethertype=ether_type) as sock:
        logging.info(f"[recv] MAC local: {sock.mac}")
        ft_handler = FileTransferHandler(src_mac=sock.mac or "")
        th = ThreadManager(socket_manager=sock, file_transfer_handler=ft_handler)

        # Instancia el receptor (registra handlers)
        FileReceiver(th, base_dir=base_dir or "")

        th.start()
        logging.info("[recv] Esperando archivos... Ctrl+C para salir")
        try:
            while not _shutdown:
                time.sleep(0.5)
        finally:
            th.stop()
            logging.info("[recv] Detenido.")

# --------------------------------------------------------------------------------------
# Modo emisor: enviar un archivo
# --------------------------------------------------------------------------------------
def run_send_file(path: str, dst_mac: str, chunk_size: int):
    interface, ether_type = read_net_env()
    logging.info(f"[send-file] Enviando archivo='{path}' a dst_mac={dst_mac} (chunk_size={chunk_size})")

    with SocketManager(interface=interface, ethertype=ether_type) as sock:
        logging.info(f"[send-file] MAC local: {sock.mac}")
        ft_handler = FileTransferHandler(src_mac=sock.mac or "")
        th = ThreadManager(socket_manager=sock, file_transfer_handler=ft_handler)

        sender = FileSender(th, chunk_size=chunk_size)

        th.start()
        try:
            file_id = sender.send_file(path=path, dst_mac=dst_mac)
            # Espera activa hasta que el contexto termine
            while True:
                ctx = th.get_ctx_by_id(file_id)
                if not ctx or ctx.finished:
                    break
                time.sleep(0.1)
            logging.info(f"[send-file] Terminado: {file_id}")
        finally:
            th.stop()

# --------------------------------------------------------------------------------------
# Modo emisor: enviar una carpeta (secuencial)
# --------------------------------------------------------------------------------------
def run_send_folder(folder: str, dst_mac: str, chunk_size: int):
    interface, ether_type = read_net_env()
    logging.info(f"[send-folder] Enviando carpeta='{folder}' a dst_mac={dst_mac} (chunk_size={chunk_size})")

    with SocketManager(interface=interface, ethertype=ether_type) as sock:
        logging.info(f"[send-folder] MAC local: {sock.mac}")
        ft_handler = FileTransferHandler(src_mac=sock.mac or "")
        th = ThreadManager(socket_manager=sock, file_transfer_handler=ft_handler)

        sender = FileSender(th, chunk_size=chunk_size)

        th.start()
        try:
            sent = sender.send_folder(folder_path=folder, dst_mac=dst_mac)
            for fid, rel in sent:
                logging.info(f"[send-folder] OK: {fid} -> {rel}")
            logging.info("[send-folder] Carpeta enviada.")
        finally:
            th.stop()

# --------------------------------------------------------------------------------------
# Arranque y CLI
# --------------------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="linkchat",
        description="CLI de pruebas para transferencia de archivos/carpeta por L2."
    )
    sub = p.add_subparsers(dest="cmd", required=False)

    # recv
    p_recv = sub.add_parser("recv", help="Modo receptor: escucha y guarda archivos.")
    p_recv.add_argument("--base-dir", dest="base_dir", default=None, help="Directorio base donde guardar (por defecto ~/Downloads/recv)")

    # send-file
    p_sf = sub.add_parser("send-file", help="Enviar un archivo.")
    p_sf.add_argument("path", help="Ruta del archivo a enviar (dentro del contenedor).")
    p_sf.add_argument("dst_mac", help="MAC destino (receptor).")
    p_sf.add_argument("--chunk", dest="chunk_size", type=int, default=int(os.environ.get("CHUNK_SIZE", "900")),
                      help="Tamaño de chunk. Si usas payload binario, ~1300 es seguro.")

    # send-folder
    p_sd = sub.add_parser("send-folder", help="Enviar una carpeta (secuencial).")
    p_sd.add_argument("folder", help="Ruta de la carpeta a enviar (dentro del contenedor).")
    p_sd.add_argument("dst_mac", help="MAC destino (receptor).")
    p_sd.add_argument("--chunk", dest="chunk_size", type=int, default=int(os.environ.get("CHUNK_SIZE", "900")),
                      help="Tamaño de chunk. Si usas payload binario, ~1300 es seguro.")

    return p

def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    parser = build_parser()
    args = parser.parse_args()

    # Si no hay subcomando, puedes dejar el modo "daemon" anterior (descubrimiento, etc.)
    # Para pruebas, usaremos CLI: si no hay comando, mostramos ayuda.
    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    if args.cmd == "recv":
        run_recv(base_dir=args.base_dir)
    elif args.cmd == "send-file":
        run_send_file(path=args.path, dst_mac=args.dst_mac, chunk_size=args.chunk_size)
    elif args.cmd == "send-folder":
        run_send_folder(folder=args.folder, dst_mac=args.dst_mac, chunk_size=args.chunk_size)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
