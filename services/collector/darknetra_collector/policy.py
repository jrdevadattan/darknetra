from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

_ONION_HOST = re.compile(r"^[a-z2-7]{56}\.onion$")
_BLOCKED_EXTENSIONS = frozenset({".apk", ".dll", ".exe", ".iso", ".jar", ".msi", ".scr", ".zip"})


class PolicyViolation(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CollectionRequest:
    url: str
    method: str
    depth: int = 0
    pages_so_far: int = 0
    bytes_so_far: int = 0


@dataclass(frozen=True)
class ValidatedCollectionRequest:
    url: str
    method: str
    depth: int


class CollectorPolicy:
    """Pure enforcement boundary used before any collector network request."""

    max_depth = 1
    max_pages = 25
    max_job_bytes = 50 * 1024 * 1024

    def validate(self, request: CollectionRequest) -> ValidatedCollectionRequest:
        method = request.method.upper()
        if method not in {"GET", "HEAD"}:
            raise PolicyViolation("METHOD_NOT_ALLOWED")
        if request.depth < 0 or request.depth > self.max_depth:
            raise PolicyViolation("DEPTH_LIMIT")
        if request.pages_so_far < 0 or request.pages_so_far >= self.max_pages:
            raise PolicyViolation("PAGE_LIMIT")
        if request.bytes_so_far < 0 or request.bytes_so_far >= self.max_job_bytes:
            raise PolicyViolation("BYTE_LIMIT")

        try:
            parsed = urlsplit(request.url)
            port = parsed.port
        except ValueError:
            raise PolicyViolation("INVALID_URL") from None
        if parsed.scheme != "http":
            raise PolicyViolation("HOST_NOT_ALLOWED")
        if parsed.username is not None or parsed.password is not None:
            raise PolicyViolation("CREDENTIALS_NOT_ALLOWED")
        if parsed.hostname is None or not _ONION_HOST.fullmatch(parsed.hostname):
            raise PolicyViolation("HOST_NOT_ALLOWED")
        if port not in {None, 80}:
            raise PolicyViolation("PORT_NOT_ALLOWED")
        lowered_path = parsed.path.casefold()
        if any(lowered_path.endswith(extension) for extension in _BLOCKED_EXTENSIONS):
            raise PolicyViolation("EXTENSION_BLOCKED")

        return ValidatedCollectionRequest(
            url=request.url,
            method=method,
            depth=request.depth,
        )


__all__ = [
    "CollectionRequest",
    "CollectorPolicy",
    "PolicyViolation",
    "ValidatedCollectionRequest",
]
