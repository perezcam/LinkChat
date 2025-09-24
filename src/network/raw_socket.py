import logging
import socket

class SocketManager:

    def __init__(self, interface: str, ethertype: int):
       
        self.interface = interface
        self.ethertype = ethertype
        self._socket = None

    def __enter__(self):
        try:
            self._socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(self.ethertype))
            self._socket.bind((self.interface, self.ethertype)) 
            logging.info(f"Socket crudo creado y vinculado a la interfaz '{self.interface}' con EtherType {hex(self.ethertype)}.")
            return self
        except PermissionError:
            logging.error("Se requieren permisos de administrador (sudo) para abrir un raw socket.")
            raise  
        except OSError as e:
            logging.error(f"Error de sistema al crear o vincular el socket en la interfaz '{self.interface}': {e}")
            raise
        except Exception as e:
            logging.error(f"Error inesperado al crear el socket: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._socket:
            self._socket.close()
            logging.info("Socket cerrado correctamente.")
        self._socket = None

    def _check_socket_open(self):
        if not self._socket:
            raise ConnectionError("El socket no está abierto. Use esta clase dentro de un bloque 'with'.")

    def send_raw_frame(self, frame: bytes):
        self._check_socket_open()
        try:
            if self._socket:
                self._socket.send(frame) 
            logging.debug(f"Trama enviada: {frame.hex()}")
        except Exception as e:
            logging.error(f"Error al enviar la trama: {e}")
            raise

    def receive_raw_frame(self, buffer_size: int = 65535) -> bytes:
        self._check_socket_open()
        try:
            if self._socket:
                frame, _ = self._socket.recvfrom(buffer_size)
            logging.debug(f"Trama recibida: {frame.hex()}")
            return frame
        except Exception as e:
            logging.error(f"Error al recibir la trama: {e}")
            raise