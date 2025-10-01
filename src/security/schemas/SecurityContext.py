from dataclasses import dataclass


@dataclass
class SecurityContext:
    enabled: bool = False
    key: bytes | None = None
    session_id : bytes | None = None

