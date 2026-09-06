"""Deterministic item validation; a valid identifier is not a finding."""

import base64
import hashlib
import re
import unicodedata
from urllib.parse import urlsplit

from darknetra.errors import PolicyDenied, Validation
from darknetra.extract.validators import LEXICON, find_crypto

SOURCE_CLASSES = {
    "evidence": None,
    "web_search": "OSINT_SURFACE",
    "onion_search": "OSINT_DARK",
    "onion_lookup": "OSINT_DARK",
    "onion_fetch": "OSINT_DARK",
    "username_lookup": "OSINT_SURFACE",
    "chain_lookup": "CHAIN",
    "sanctions_check": "CHAIN",
    "keyserver_lookup": "OSINT_SURFACE",
    "telegram_channel_read": "TELEGRAM",
}
DEFAULTS = {
    "KEYWORD": (["web_search", "onion_search"], 21600),
    "ALIAS": (["web_search", "onion_search", "username_lookup"], 21600),
    "WALLET": (["chain_lookup", "sanctions_check"], 3600),
    "PGP_FINGERPRINT": (["keyserver_lookup", "onion_search"], 86400),
    "ONION_DOMAIN": (["onion_lookup", "onion_fetch"], 21600),
    "TELEGRAM_CHANNEL": (["telegram_channel_read"], 1800),
    "IMAGE_HASH": (["evidence"], 60),
}
ALLOWED_SOURCES = {kind: set(sources) | {"evidence"} for kind, (sources, _) in DEFAULTS.items()}


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).strip().split()).casefold()


def validate_item(kind: str, value: str, variants: list[str] | None = None):
    if kind not in DEFAULTS or not value.strip() or len(value) > 1000:
        raise Validation("Invalid watchlist type or value")
    normalized = normalize(value)
    if kind == "ALIAS":
        normalized = normalized.removeprefix("@")
        if not re.fullmatch(r"[\w.-]{1,100}", normalized):
            raise Validation("Invalid alias")
    elif kind == "WALLET":
        candidates = [c for c in find_crypto(value.strip()) if c.valid and c.raw == value.strip()]
        if not candidates:
            raise Validation("Wallet must have a supported valid checksum")
        normalized = candidates[0].normalized["value"]
    elif kind == "PGP_FINGERPRINT":
        normalized = re.sub(r"\s", "", value).upper()
        if not re.fullmatch(r"[0-9A-F]{40}", normalized):
            raise Validation("Fingerprint must contain 40 hexadecimal characters")
    elif kind == "ONION_DOMAIN":
        normalized = value.strip().lower().removesuffix(".")
        if not re.fullmatch(r"[a-z2-7]{56}\.onion", normalized):
            raise Validation("Onion domain must be version 3")
        decoded = base64.b32decode(normalized[:-6].upper())
        checksum = hashlib.sha3_256(b".onion checksum" + decoded[:32] + b"\x03").digest()[:2]
        if decoded[-1] != 3 or decoded[32:34] != checksum:
            raise Validation("Invalid version 3 onion checksum")
    elif kind == "TELEGRAM_CHANNEL":
        if normalized.startswith(("https://t.me/", "http://t.me/", "t.me/")):
            parsed = urlsplit(normalized if "://" in normalized else "https://" + normalized)
            if parsed.query or parsed.fragment or parsed.hostname != "t.me":
                raise Validation("Only public channel names are supported")
            normalized = parsed.path.removeprefix("/")
        normalized = normalized.removeprefix("@")
        if not re.fullmatch(r"[a-z][a-z0-9_]{4,31}", normalized):
            raise Validation("Only public channel names are supported")
    elif kind == "IMAGE_HASH":
        if not re.fullmatch(r"[a-f0-9]{16}", normalized):
            raise Validation("Image hash must contain 16 hexadecimal characters")
    values = [normalized] + [normalize(v) for v in variants or [] if v.strip()]
    if kind == "KEYWORD":
        for _, (_, terms) in LEXICON.items():
            for term in terms:
                if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized):
                    values.extend(normalized.replace(term, alternate) for alternate in terms)
    if len(values) > 100 or any(len(v) > 1000 for v in values):
        raise Validation("Too many or oversized variants")
    return normalized, list(dict.fromkeys(values))


def sources_for(kind: str, requested: list[str], case, settings) -> list[str]:
    sources = list(dict.fromkeys(requested))
    if not sources:
        sources = ["evidence"] if settings.offline_mode or case.demo else DEFAULTS[kind][0]
        sources = [
            s
            for s in sources
            if SOURCE_CLASSES[s] is None
            or SOURCE_CLASSES[s] in case.source_policy["allowed_source_classes"]
        ]
        sources = [
            s for s in sources if s != "onion_fetch" or case.source_policy.get("tor_enabled")
        ]
        sources = [
            s
            for s in sources
            if s != "telegram_channel_read" or case.source_policy.get("telegram_enabled")
        ]
        sources = [
            s
            for s in sources
            if s != "username_lookup" or case.source_policy.get("person_lookup_enabled")
        ]
    if not sources:
        raise PolicyDenied("No monitoring source is permitted by this case")
    for source in sources:
        if source not in ALLOWED_SOURCES[kind]:
            raise Validation("Unsupported source for this item type")
        source_class = SOURCE_CLASSES[source]
        if source == "evidence" and not set(case.source_policy["allowed_source_classes"]) - {
            "REPORT"
        }:
            raise PolicyDenied("No stored evidence source is permitted by this case")
        if source_class and source_class not in case.source_policy["allowed_source_classes"]:
            raise PolicyDenied("Monitoring source is disabled by case policy")
        if source == "onion_fetch" and not case.source_policy.get("tor_enabled"):
            raise PolicyDenied("Tor is disabled for this case")
        if source == "telegram_channel_read" and not case.source_policy.get("telegram_enabled"):
            raise PolicyDenied("Telegram is disabled for this case")
        if source == "username_lookup" and not case.source_policy.get("person_lookup_enabled"):
            raise PolicyDenied("Person lookup is disabled for this case")
    return sources
