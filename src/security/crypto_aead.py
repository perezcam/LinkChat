from src.security.schemas.SecurityContext import SecurityContext
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

class SecurityManager:
    def __init__(self) -> None:
        self._sec = SecurityContext()

    def set_security(self, key: bytes, session_id: bytes):
        if len(key) != 32:
            raise ValueError("ChaCha20-Poly1305 requires 32 bytes key")
        if len(session_id) != 8:
            raise ValueError("Session id must be of 8 bytes")
        self._sec.key = key
        self._sec.session_id = session_id
        self._sec.enabled = True 

    def _build_nonce(self, sequence_u32: int) -> bytes:
        if self._sec.session_id is None:
            raise ValueError("SecurityContext.session_id not initialized")
        return self._sec.session_id + sequence_u32.to_bytes(4, 'big')

    def encrypt(self, payload: bytes, aad: bytes, sequence_u32: int) -> bytes:
        if not self._sec.enabled or not self._sec.key:
            return payload              #compatible without encryption
        aead = ChaCha20Poly1305(self._sec.key)
        nonce = self._build_nonce(sequence_u32)
        return aead.encrypt(nonce, payload, aad)  # ciphertext||tag (16B)
    
    def decrypt(self, ciphertext_and_tag: bytes, aad: bytes, sequence_u32: int) -> bytes:
        if not self._sec.enabled or not self._sec.key:
            return ciphertext_and_tag
        aead = ChaCha20Poly1305(self._sec.key)
        nonce = self._build_nonce(sequence_u32)
        return aead.decrypt(nonce, ciphertext_and_tag, aad)