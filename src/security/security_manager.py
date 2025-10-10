


import hashlib
import hmac
import secrets
from src.core.enums.enums import MessageType
from src.core.schemas.frame_schemas import FrameSchema, HeaderSchema
from src.security.security_handler import SecurityHandler


class SecurityManager:
    def __init__(self, pre_shared_key: bytes, sec_handler: SecurityHandler) -> None:
        self._pre_shared_key = pre_shared_key
        self.handler = sec_handler

        self._nonce_len = 12
        self._version = 1
        self._tag_len = 16

    def _should_protect(self, message_type: MessageType) -> bool:
        return message_type not in (
            MessageType.DISCOVER_REQUEST,
            MessageType.DISCOVER_REPLY,
        )
    
    def protect_outgoing(self, frame: FrameSchema) -> FrameSchema:
        """Encrypts and authenticates an outgoing frame."""
        if not self._should_protect(frame.header.message_type):
            return frame
        
        ## Generate a random nonce (unique per frame)
        nonce = secrets.token_bytes(self._nonce_len)

        # Derive encryption and authentication keys from the PSK and nonce
        key_enc = self.handler.hkdf_sha256(self._pre_shared_key, nonce, b"enc", 32)
        key_mac = self.handler.hkdf_sha256(self._pre_shared_key, nonce, b"mac", 32)

        # Prepare additional authenticated data (AAD)
        aad = self.handler.aad_for(frame)

        # Encrypt payload using XOR-based stream cipher
        payload = frame.payload
        keystream = self.handler.keystream(key_enc, nonce, len(payload))
        ciphertext = bytes(a ^ b for a, b in zip(payload, keystream))

        # Compute authentication tag (HMAC)
        tag = hmac.new(key_mac, aad + nonce + ciphertext, hashlib.sha256).digest()[:self._tag_len]


        out_payload = bytes([self._version]) + nonce + ciphertext + tag
        out_frame = FrameSchema(
            dst_mac=frame.dst_mac,
            src_mac=frame.src_mac,
            ethertype=frame.ethertype,
            header=HeaderSchema(
                message_type=frame.header.message_type,
                sequence=frame.header.sequence,
                payload_len=len(out_payload)
            ),
            payload=out_payload
        )

        print("security: Se encripto el frame, payload: ", out_payload)

        return out_frame
    
    def accept_incoming(self, frame: FrameSchema) -> FrameSchema | None:
        """Verifies and decrypts an incoming protected frame."""
        if not self._should_protect(frame.header.message_type):
            return frame
        
        data = frame.payload
        if len(data) < 1 + self._nonce_len + self._tag_len or data[0] != self._version:
            #Looks like an unprotected payload
            return None
        
        nonce = data[1:1+self._nonce_len]
        tag = data[-self._tag_len:]
        ciphertext  = data[1+self._nonce_len:-self._tag_len]

        # Re-derive encryption and authentication keys
        k_enc = self.handler.hkdf_sha256(self._pre_shared_key, nonce, b"enc", 32)
        k_mac = self.handler.hkdf_sha256(self._pre_shared_key, nonce, b"mac", 32)

        # Verify authentication tag
        aad = self.handler.aad_for(frame)
        exp = hmac.new(k_mac, aad + nonce + ciphertext, hashlib.sha256).digest()[:self._tag_len]
        if not hmac.compare_digest(tag, exp):
            return None  # Invalid tag
        
        # Decrypt payload using XOR with generated keystream
        keystream = self.handler.keystream(k_enc, nonce, len(ciphertext))
        payload_decrypt = bytes(a ^ b for a, b in zip(ciphertext, keystream))

        out_frame = FrameSchema(
            dst_mac=frame.dst_mac,
            src_mac=frame.src_mac,
            ethertype=frame.ethertype,
            header = HeaderSchema(
                message_type=frame.header.message_type,
                sequence=frame.header.sequence,
                payload_len=len(payload_decrypt)
            ),
            payload=payload_decrypt
        )

        print("security: Se desencripto el frame, payload: ", payload_decrypt)

        return out_frame






    