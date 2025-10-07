import os, socket, pathlib

DEFAULT_ETHER_TYPE = "0x88B5"  

VIRTUAL_PREFIXES = ("lo", "docker", "br-", "veth", "tun", "tap", "vmnet", "tailscale", "wg")

def _parse_ethertype(val: str) -> int:
    # Soporta "0x88B5" o "34933"
    return int(str(val).strip(), 0)

def get_ether_type() -> int:
    return _parse_ethertype(os.environ.get("ETHER_TYPE", DEFAULT_ETHER_TYPE))

def _is_candidate(ifname: str) -> bool:
    if any(ifname.startswith(p) for p in VIRTUAL_PREFIXES):
        return False
    base = pathlib.Path("/sys/class/net") / ifname
    return base.exists()

def _operstate(ifname: str) -> str:
    try:
        return (pathlib.Path("/sys/class/net")/ifname/"operstate").read_text().strip()
    except Exception:
        return "unknown"

def _is_wireless(ifname: str) -> bool:
    return (pathlib.Path("/sys/class/net")/ifname/"wireless").exists()

def _list_ifaces() -> list[str]:
    try:
        return [p.name for p in pathlib.Path("/sys/class/net").iterdir()]
    except Exception:
        return []

def _pick_interface() -> str | None:
    # Preferir cableadas UP, luego Wi-Fi UP, luego cualquiera UP
    ifaces = [i for i in _list_ifaces() if _is_candidate(i)]
    wired_up = [i for i in ifaces if not _is_wireless(i) and _operstate(i) == "up"]
    wifi_up  = [i for i in ifaces if _is_wireless(i) and _operstate(i) == "up"]
    any_up   = [i for i in ifaces if _operstate(i) == "up"]

    for group in (wired_up, wifi_up, any_up):
        if group:
            return group[0]
    return ifaces[0] if ifaces else None

def get_interface() -> str:
    # 1) Respeta env si existe y es válida
    env_if = os.environ.get("INTERFACE")
    if env_if and _is_candidate(env_if):
        return env_if
    # 2) Autodetecta
    picked = _pick_interface()
    if picked:
        return picked
    # 3) Fallback común en contenedores con network_mode: host
    return "eth0"

def get_alias() -> str:
    # Prioriza envs; cae al hostname si no hay
    return (
        os.environ.get("ALIAS")
        or os.environ.get("NODE_ALIAS")
        or socket.gethostname()
    )

def get_runtime_config() -> dict:
    return {
        "interface": get_interface(),     
        "ethertype": get_ether_type(),    
        "alias": get_alias(),
    }
