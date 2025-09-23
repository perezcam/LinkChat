import struct

from enums.formats import HeaderFormat

ETHER_TYPE = 0x88B5  #TODO: definir en archivo


def _decode_header(frame):
    
    header = frame[14:22]  

    header_format = HeaderFormat.get_format()
    message_type, sequence, payload_len, _ = struct.unpack(header_format, header)

    return {
        'message_type': message_type,
        'sequence': sequence,
        'payload_len': payload_len
    }

def decode_ethernet_frame(frame):
    
    dst_mac = ':'.join(format(x, '02x') for x in frame[:6]) 
    src_mac = ':'.join(format(x, '02x') for x in frame[6:12])

    header_data = _decode_header(frame)

    payload = frame[22:22 + header_data['payload_len']].decode('utf-8')

    return {
        'dst_mac': dst_mac,
        'src_mac': src_mac,
        'message_type': header_data['message_type'],
        'sequence': header_data['sequence'],
        'payload': payload
    }


#TODO: Descartar aqui los que no sean de mi EtherTYpe??? o hacerlo en el pool de hilos?
