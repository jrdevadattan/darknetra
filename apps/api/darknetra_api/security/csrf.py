import hashlib
import hmac
import secrets


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_csrf_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_csrf_token(token: str, expected_hash: str) -> bool:
    supplied_hash = hash_csrf_token(token)
    return hmac.compare_digest(supplied_hash, expected_hash)
