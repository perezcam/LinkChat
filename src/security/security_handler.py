import hashlib
import hmac
import struct

from src.core.schemas.frame_schemas import FrameSchema


class SecurityHandler:
    def __init__(self) -> None:
        pass 

    def keystream(self, k_enc: bytes, nonce: bytes, nbytes: int) -> bytes:
        """Generates a pseudo-random byte stream using HMAC-SHA256 over (nonce || counter) blocks."""
        out = bytearray()
        counter = 0
        while len(out) < nbytes:
            # Each block is HMAC(key_enc, nonce || counter_be32); blocks are concatenated until enough bytes exist
            blk = hmac.new(k_enc, nonce + struct.pack(">I", counter), hashlib.sha256).digest()
            out.extend(blk)
            counter += 1
        return bytes(out[:nbytes])

    def aad_for(self, frame: FrameSchema) -> bytes:
        """Builds Additional Authenticated Data from frame headers to protect non-encrypted header fields."""
        aad = f"{frame.src_mac}|{frame.dst_mac}|{frame.ethertype}|{frame.header.message_type}|{frame.header.sequence}"
        return aad.encode("utf-8")

    def _hkdf_extract(self, nonce: bytes, preshared_key: bytes):
        """HKDF-Extract step: mixes the PSK with a salt (nonce) to produce a pseudorandom key (PRK)."""
        return hmac.new(nonce, preshared_key, hashlib.sha256).digest()
    
    def _hkdf_expand(self, prk: bytes, info: bytes, length: int):
        """HKDF-Expand step: expands the PRK into context-separated key material labeled by 'info'."""
        out, t = bytearray(), b""
        counter = 1
        while len(out) < length:
            # Standard HKDF chaining: T(i) = HMAC(PRK, T(i-1) || info || counter)
            t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
            out.extend(t)
            counter += 1
        return bytes(out[:length])
    
    def hkdf_sha256(self, preshared_key: bytes, nonce: bytes, info: bytes, length: int) -> bytes:
        """Derives context-specific subkeys from a PSK using HKDF-SHA256 with the given nonce as salt."""
        pseudo_random_key = self._hkdf_extract(nonce or b"\x00"*32, preshared_key)
        return self._hkdf_expand(pseudo_random_key, info, length)
    
