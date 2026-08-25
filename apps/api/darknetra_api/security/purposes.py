"""Canonical context strings for encrypted application fields."""

from __future__ import annotations

import json

_SENSITIVE_FIELD_PURPOSE_PREFIX = "darknetra-sensitive-reveal:v1:"


def compose_sensitive_field_purpose(resource_type: str, field_name: str) -> str:
    """Compose an injective, stable purpose shared by writers and readers."""

    if not isinstance(resource_type, str) or not resource_type:
        raise ValueError("resource_type must be a non-empty string")
    if not isinstance(field_name, str) or not field_name:
        raise ValueError("field_name must be a non-empty string")
    components = json.dumps(
        [resource_type, field_name],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"{_SENSITIVE_FIELD_PURPOSE_PREFIX}{components}"


__all__ = ["compose_sensitive_field_purpose"]
