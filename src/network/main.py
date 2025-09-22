import struct

from enums.enums import MessageType
from frame_creator import create_ethernet_frame
from frame_decoder import decode_ethernet_frame


# Definir el EtherType para tu protocolo LinkChat
ETHER_TYPE = 0x88B5  # Este será el EtherType para tu protocolo LinkChat


# Función principal de prueba
def main():
    # Ejemplo de parámetros
    src_mac = "00:14:22:01:23:45"
    dst_mac = "00:14:22:67:89:ab"
    payload = "Hola"  # Mensaje a enviar
    message_type = MessageType.HELLO  # Tipo de mensaje (HELLO)
    sequence = 1  # Primer mensaje

    # Crear la trama Ethernet
    frame = create_ethernet_frame(src_mac, dst_mac, payload, message_type, sequence, ETHER_TYPE)

    # Imprimir la cadena de bytes de la trama
    print(f"Trama Ethernet creada (en bytes): {frame}")

    # Decodificar la trama y mostrar el resultado
    decoded_header = decode_ethernet_frame(frame)
    print(f"Trama decodificada: {decoded_header}")

if __name__ == "__main__":
    main()
