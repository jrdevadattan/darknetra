"""Deterministic derivation-parameter identity."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

_DOMAIN = b"DARKNETRA-DERIVATION-PARAMETERS\x00v1\x00"


def _normalize_canonical_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(
                "derivation parameters numbers must be finite and integer-valued"
            )
        return int(value)
    if isinstance(value, list | tuple):
        return [_normalize_canonical_json_value(item) for item in value]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("derivation parameter object keys must be strings")
        return {
            key: _normalize_canonical_json_value(item)
            for key, item in value.items()
        }
    raise ValueError("derivation parameters must contain supported JSON values")


def canonical_derivation_parameters_json(parameters: Mapping[str, Any]) -> bytes:
    try:
        normalized = _normalize_canonical_json_value(parameters)
        rendered = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except TypeError as exc:
        raise ValueError("derivation parameters must contain supported JSON values") from exc
    return rendered.encode("utf-8")


def derivation_parameters_digest(parameters: Mapping[str, Any]) -> str:
    return hashlib.sha256(_DOMAIN + canonical_derivation_parameters_json(parameters)).hexdigest()


__all__ = ["canonical_derivation_parameters_json", "derivation_parameters_digest"]
