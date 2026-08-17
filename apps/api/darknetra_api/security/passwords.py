from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_password_hasher = PasswordHasher()


class PasswordPolicyError(ValueError):
    """Raised when a supplied password violates the local password policy."""


def validate_password_policy(password: str, *, username: str) -> None:
    if "\x00" in password:
        raise PasswordPolicyError("password must not contain NUL characters")
    if not 12 <= len(password) <= 128:
        raise PasswordPolicyError("password length must be between 12 and 128 characters")
    if password.casefold() == username.casefold():
        raise PasswordPolicyError("password must not equal the username")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return _password_hasher.verify(encoded_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False
