"""Deterministic export masking, applied to every text-bearing report section."""

import hashlib
import re

import phonenumbers

URL = re.compile(r"https?://[^\s<>\]\"']+|\b[a-z2-7]{56}\.onion\b", re.I)
EMAIL = re.compile(r"\b([\w.+-]+)@([\w.-]+\.[A-Za-z]{2,})\b")


def text(value: str) -> str:
    value = URL.sub(lambda m: "locator:" + hashlib.sha256(m[0].encode()).hexdigest()[:12], value)
    value = EMAIL.sub(lambda m: m[1][:1] + "***@" + m[2], value)
    # Keep the same region and matching rules as deterministic phone extraction.
    # Replace from the end so earlier offsets remain valid for multiple matches.
    for match in reversed(list(phonenumbers.PhoneNumberMatcher(value, "IN"))):
        national = phonenumbers.national_significant_number(match.number)
        masked = f"+{match.number.country_code} xxxxx {national[-3:]}"
        value = value[: match.start] + masked + value[match.end :]
    return value


def redact(value, key=""):
    if key == "authority_reference":
        return "[withheld]"
    if key.endswith(("_id", "_ids", "_hash", "_digest")) or key in {
        "sha256",
        "storage_key",
        "evidence_id",
        "id",
        "case_id",
        "code",
        "hash",
        "config_digest",
    }:
        return value
    if isinstance(value, str):
        return text(value)
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    return value
