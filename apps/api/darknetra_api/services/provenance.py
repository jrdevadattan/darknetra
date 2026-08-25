"""Deterministic derivation-parameter identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

_DOMAIN = b"DARKNETRA-DERIVATION-PARAMETERS\x00v1\x00"
MAX_CANONICAL_INTEGER_DIGITS = 1000
_CANONICAL_INTEGER_LIMIT = 10**MAX_CANONICAL_INTEGER_DIGITS


def _validate_canonical_integer(value: int) -> int:
    if abs(value) >= _CANONICAL_INTEGER_LIMIT:
        raise ValueError(
            "derivation parameters integers must contain at most "
            "1,000 decimal digits"
        )
    return value


def _normalize_canonical_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return _validate_canonical_integer(value)
    if isinstance(value, float):
        try:
            emitted_token = json.dumps(value, allow_nan=False)
            decimal_value = Decimal(emitted_token)
        except (ValueError, InvalidOperation) as exc:
            raise ValueError(
                "derivation parameters numbers must be finite and integer-valued"
            ) from exc
        if decimal_value != decimal_value.to_integral_value():
            raise ValueError(
                "derivation parameters numbers must be finite and integer-valued"
            )
        return _validate_canonical_integer(int(decimal_value))
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


__all__ = [
    "MAX_CANONICAL_INTEGER_DIGITS",
    "canonical_derivation_parameters_json",
    "derivation_parameters_digest",
]
