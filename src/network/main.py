from raw_socket import SocketManager
from service_threads import ServiceThreads

ETHER_TYPE = 0x88B5

def on_neighbors_changed(neighs: dict):
    # Muestra vecinos cada vez que cambien
    resumen = [{ "mac": mac, "alias": v["alias"] } for mac, v in neighs.items()]
    print("[app] vecinos =", resumen)

def main():
    iface = "eth0"          # o la que uses
    src_mac = "aa:bb:cc:dd:ee:ff"  # pasa aquí tu MAC ya normalizada
    alias = "Nodo-Camilo"

    sock = SocketManager(interface=iface, ethertype=ETHER_TYPE)
    sock.create_raw_socket()

    svc = ServiceThreads(sock=sock, src_mac=src_mac, alias=alias)
    svc.set_on_neighbors_changed(on_neighbors_changed)
    svc.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        svc.stop()
        sock.close_socket()

if __name__ == "__main__":
    import time
    main()
