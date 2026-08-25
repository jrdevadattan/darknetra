import re

KEY_VERSION_MAX_LENGTH = 64
_KEY_VERSION_PATTERN = re.compile(
    rf"v[1-9][0-9]{{0,{KEY_VERSION_MAX_LENGTH - 2}}}\Z",
    flags=re.ASCII,
)


def validate_key_version(value: object) -> str:
    """Return a valid persisted key version or reject it with one shared error."""

    if not isinstance(value, str) or _KEY_VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid sensitive field key version")
    return value


__all__ = ["KEY_VERSION_MAX_LENGTH", "validate_key_version"]
