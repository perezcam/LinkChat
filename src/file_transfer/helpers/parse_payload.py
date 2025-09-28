from typing import Dict


def parse_payload(s: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in s.splitlines():
        if not line:
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out