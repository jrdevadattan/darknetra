"""Deterministic derivation-parameter identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

_DOMAIN = b"DARKNETRA-DERIVATION-PARAMETERS\x00v1\x00"


def canonical_derivation_parameters_json(parameters: Mapping[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            dict(parameters),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("derivation parameters must contain finite JSON values") from exc
    return rendered.encode("utf-8")


def derivation_parameters_digest(parameters: Mapping[str, Any]) -> str:
    return hashlib.sha256(_DOMAIN + canonical_derivation_parameters_json(parameters)).hexdigest()


__all__ = ["canonical_derivation_parameters_json", "derivation_parameters_digest"]
