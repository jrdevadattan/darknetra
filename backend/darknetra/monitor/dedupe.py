"""Stable fingerprints exclude search ranking, fragments and tracking parameters."""

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from darknetra.monitor.validation import normalize


def normalized_url(url: str) -> str:
    parts = urlsplit(url)
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query)
        if not k.casefold().startswith("utm_") and k not in {"fbclid", "gclid"}
    )
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(query), "")
    )


def url_hash(url: str) -> str:
    return hashlib.sha256(normalized_url(url).encode()).hexdigest()


def content_hash(
    url: str, excerpt: str, *, body_hash: str | None = None, event_id: str | None = None
) -> str:
    # A captured body checksum distinguishes actual changes from rewritten snippets.
    identity = (
        "event:" + event_id
        if event_id
        else normalized_url(url) + "\n" + (body_hash or normalize(excerpt[:4000]))
    )
    return hashlib.sha256(identity.encode()).hexdigest()
