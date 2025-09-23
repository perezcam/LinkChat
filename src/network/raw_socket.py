import socket

class SocketManager:

    def __init__(self, interface: str, ethertype: int):
        self.interface = interface
        self.ethertype = ethertype
        self._socket = None

    def create_raw_socket(self):
        if self._socket: 
            print("el _socket ya esta creado")
            return
        try:
            self._socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(self.ethertype))
            self._socket.bind((self.interface, self.ethertype))

            print(f"socket crudo creado y vinculado a la interfaz {self.interface} con EtherType {hex(self.ethertype)}")
        except PermissionError:
            print("Error: Se requieren permisos de administrador para abrir un raw _socket.")
        except Exception as e:
            print(f"Error al crear el _socket: {e}")

    def send_raw_frame(self, frame: bytes):

        if not self._socket:
            self.create_raw_socket()

        if self._socket:
            self._socket.send(frame)
            print(f"Trama enviada: {frame.hex()}")

    def receive_raw_frame(self):
        if not self._socket:
            self.create_raw_socket()

        if self._socket:
            frame, _ = self._socket.recvfrom(65535)  # Maximum bytes that can receive
            print(f"Trama recibida: {frame.hex()}")
            return frame
        


    def close_socket(self):

        if self._socket:
            self._socket.close()
            print("_socket cerrado correctamente.")
        else:
            print("Error: _socket no está creado. No se puede cerrar.")


#FIXME:BORRAR LOS PRINTS