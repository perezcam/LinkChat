import socket


def open_raw_socket(interface, ethertype):
    """
    Abre un socket crudo en la interfaz proporcionada.
    """
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
    s.bind((interface, ethertype))
    return s

def send_raw_frame(s, frame):
    """
    Envía una trama a través de un socket crudo.
    """
    s.send(frame)

def receive_raw_frame(s):
    """
    Recibe una trama a través de un socket crudo.
    """
    return s.recv(65535)  # Tamaño máximo de una trama Ethernet
