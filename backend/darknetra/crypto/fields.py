import hashlib
import hmac
import secrets
import unicodedata

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class FieldCipher:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256 requires a 32-byte key")
        self._key = key
        self._cipher = AESGCM(key)

    def encrypt(self, plaintext: str, aad: str) -> bytes:
        nonce = secrets.token_bytes(12)
        return (
            b"\x01"
            + nonce
            + self._cipher.encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
        )

    def decrypt(self, blob: bytes, aad: str) -> str:
        if len(blob) < 29 or blob[0] != 1:
            raise ValueError("Unsupported encrypted field envelope")
        try:
            return self._cipher.decrypt(blob[1:13], blob[13:], aad.encode("utf-8")).decode("utf-8")
        except (InvalidTag, UnicodeDecodeError):
            raise ValueError("Encrypted field authentication failed") from None

    def blind_index(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).strip().casefold()
        return hmac.new(
            self._key, b"darknetra:blind-index:v1:" + normalized.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:32]
