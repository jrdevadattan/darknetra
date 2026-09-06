"""Deterministic candidates; validity is not an assertion about identity or conduct."""

import hashlib
import math
import re
from dataclasses import dataclass, field

import base58
import pgpy
import phonenumbers
from bech32 import bech32_hrp_expand, bech32_polymod, convertbits
from eth_utils import is_checksum_address


@dataclass
class Candidate:
    type: str
    raw: str
    normalized: dict
    start: int
    end: int
    validator: str
    valid: bool = True
    confidence: float = 0.9
    meta: dict = field(default_factory=dict)


def segwit(address):
    if address.lower() != address and address.upper() != address:
        return False, {}
    value = address.lower()
    hrp, _, encoded = value.rpartition("1")
    alphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    if (
        hrp not in {"bc", "tb"}
        or len(encoded) < 7
        or any(c not in alphabet for c in encoded)
        or len(value) > 90
    ):
        return False, {}
    data = [alphabet.index(c) for c in encoded]
    version = data[0]
    program = convertbits(data[1:-6], 5, 8, False)
    residue = bech32_polymod(bech32_hrp_expand(hrp) + data)
    valid = version <= 16 and program is not None and 2 <= len(program) <= 40
    valid = valid and residue == (1 if version == 0 else 0x2BC830A3)
    valid = valid and (version != 0 or len(program) in {20, 32})
    return bool(valid), {
        "network": "testnet" if hrp == "tb" else "mainnet",
        "witness_version": version,
    }


def find_crypto(text):
    out = []
    patterns = [
        (
            "BTC_ADDRESS",
            r"\b(?:[13mn2][a-km-zA-HJ-NP-Z1-9]{25,34}|(?:bc1|tb1)[a-zA-Z0-9]{25,87})\b",
        ),
        ("ETH_ADDRESS", r"\b0x[0-9a-fA-F]{40}\b"),
        ("TRON_ADDRESS", r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b"),
        ("XMR_ADDRESS", r"\b[48][0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b"),
    ]
    for kind, pattern in patterns:
        for m in re.finditer(pattern, text):
            raw, meta, valid, validator = m[0], {}, False, "base58check"
            if kind == "ETH_ADDRESS":
                body = raw[2:]
                checksum = (
                    "all_lower"
                    if body == body.lower()
                    else "all_upper"
                    if body == body.upper()
                    else "valid_checksum"
                    if is_checksum_address(raw)
                    else "invalid_checksum"
                )
                valid, validator, meta = (
                    checksum != "invalid_checksum",
                    "eip55",
                    {"checksum": checksum},
                )
            elif kind == "XMR_ADDRESS":
                valid, validator, meta = (
                    False,
                    "shape",
                    {"traceable": False, "checksum_unverified": True},
                )
            elif raw.lower().startswith(("bc1", "tb1")):
                valid, meta = segwit(raw)
                validator = "bech32_checksum"
            else:
                try:
                    payload = base58.b58decode_check(raw)
                    valid = len(payload) == 21 and payload[0] in (
                        {0x41} if kind == "TRON_ADDRESS" else {0, 5, 111, 196}
                    )
                    meta = {"network": "testnet" if payload[0] in {111, 196} else "mainnet"}
                except ValueError:
                    pass
            out.append(
                Candidate(
                    kind,
                    raw,
                    {"value": raw.lower() if kind == "ETH_ADDRESS" else raw},
                    *m.span(),
                    validator,
                    valid,
                    1.0 if valid else 0.3,
                    meta,
                )
            )
    return out


def find_pgp(text):
    out, computed = [], []
    for m in re.finditer(
        r"-----BEGIN PGP (PUBLIC|PRIVATE) KEY BLOCK-----.*?-----END PGP \1 KEY BLOCK-----",
        text,
        re.S,
    ):
        if m[1] == "PRIVATE":
            # Do not replicate secret material into observations.
            continue
        try:
            key, _ = pgpy.PGPKey.from_blob(m[0])
            if not key.is_public:
                continue
            fingerprint = str(key.fingerprint).replace(" ", "").upper()
            computed.append((m.start(), m.end(), fingerprint))
            out.append(
                Candidate(
                    "PGP_FINGERPRINT",
                    m[0],
                    {"value": fingerprint},
                    *m.span(),
                    "pgpy_computed",
                    True,
                    1.0,
                )
            )
        except (ValueError, TypeError, IndexError, NotImplementedError):
            out.append(
                Candidate(
                    "PGP_KEY",
                    m[0],
                    {"value": hashlib.sha256(m[0].encode()).hexdigest()},
                    *m.span(),
                    "pgpy",
                    False,
                    0.3,
                )
            )
    for m in re.finditer(
        r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{4}[ \u00a0]?){9}[0-9A-Fa-f]{4}(?![0-9A-Fa-f])", text
    ):
        fingerprint = re.sub(r"\s", "", m[0]).upper()
        mismatch = any(
            min(abs(m.start() - end), abs(start - m.end())) < 300 and fp != fingerprint
            for start, end, fp in computed
        )
        out.append(
            Candidate(
                "PGP_FINGERPRINT",
                m[0],
                {"value": fingerprint},
                *m.span(),
                "regex",
                False,
                0.6,
                {"mismatch": mismatch, "computed": False},
            )
        )
    return out


LEXICON = {
    "heroin": ("SUBSTANCE", ["chitta", "ਚਿੱਟਾ", "चिट्टा"]),
    "generic_drug_term": ("SLANG", ["maal", "ਮਾਲ", "माल"]),
    "white_ambiguous": ("SLANG", ["safed", "ਸਫੇਦ", "सफेद"]),
    "Zirakpur": ("LOCATION", ["zirakpur", "ज़ीरकपुर", "ਜ਼ੀਰਕਪੁਰ"]),
    "courier_delivery": ("SHIPPING_TERM", ["courier", "delivery", "bhej dunga"]),
}


def find_candidates(text):
    out = find_crypto(text) + find_pgp(text)
    for match in phonenumbers.PhoneNumberMatcher(text, "IN"):
        value = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
        out.append(
            Candidate(
                "PHONE",
                match.raw_string,
                {"value": value},
                match.start,
                match.end,
                "phonenumbers",
                True,
                0.9,
            )
        )
    for kind, pattern, validator in [
        ("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "email_regex"),
        ("CONTACT_HANDLE", r"(?<![\w@])@[A-Za-z0-9_.]{3,32}\b", "handle_regex"),
        ("CONTACT_HANDLE", r"(?i)wickr[:\s-]+[A-Za-z0-9_.-]{3,32}", "wickr_regex"),
        ("URL", r"https?://[^\s<>\"']+", "url_regex"),
        ("ONION_LOCATOR", r"\b[a-z2-7]{56}\.onion\b", "v3_shape"),
    ]:
        for m in re.finditer(pattern, text):
            out.append(Candidate(kind, m[0], {"value": m[0].casefold()}, *m.span(), validator))
    for m in re.finditer(
        r"(?i)(₹|Rs\.?|INR|USD|\$|USDT|TRX)\s*(\d[\d,]*(?:\.\d+)?)(?:\s*(k|lakh))?\b", text
    ):
        amount = (
            float(m[2].replace(",", ""))
            * {None: 1, "k": 1000, "lakh": 100000}[m[3].lower() if m[3] else None]
        )
        if not math.isfinite(amount):
            continue
        currency = (
            "INR"
            if m[1].lower() in {"₹", "rs", "rs.", "inr"}
            else "USD"
            if m[1] == "$"
            else m[1].upper()
        )
        out.append(
            Candidate(
                "PRICE", m[0], {"amount": amount, "currency": currency}, *m.span(), "commerce"
            )
        )
        continuation = re.match(r"\s*[-–]\s*(\d[\d,]*(?:\.\d+)?)\b", text[m.end() :])
        if continuation:
            upper = float(continuation[1].replace(",", ""))
            if math.isfinite(upper):
                out[-1].meta["range"] = True
                start, end = continuation.span(1)
                out.append(
                    Candidate(
                        "PRICE",
                        continuation[1],
                        {"amount": upper, "currency": currency},
                        m.end() + start,
                        m.end() + end,
                        "commerce",
                        meta={"range": True},
                    )
                )
    for m in re.finditer(
        r"(?i)\b(\d+(?:\.\d+)?|ek|do|adha|एक|दो|ਆਧਾ|ਦੋ)\s*(kg|gms?|grams?|tola|pcs|pieces|ml|tabs?)\b",
        text,
    ):
        words = {"ek": 1, "do": 2, "adha": 0.5, "एक": 1, "दो": 2, "ਆਧਾ": 0.5, "ਦੋ": 2}
        value = words[m[1].lower()] if m[1].lower() in words else float(m[1])
        if not math.isfinite(value):
            continue
        unit = m[2].lower()
        normalized = {"value": value, "unit": unit}
        if unit in {"kg", "g", "gm", "gms", "gram", "grams", "tola"}:
            normalized["grams"] = value * {"kg": 1000, "tola": 11.6638}.get(unit, 1)
        out.append(Candidate("QUANTITY", m[0], normalized, *m.span(), "commerce"))
    for canonical, (kind, terms) in LEXICON.items():
        for term in terms:
            for m in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I):
                out.append(
                    Candidate(
                        kind,
                        m[0],
                        {"value": canonical},
                        *m.span(),
                        "lexicon_exact",
                        True,
                        0.5 if "ambiguous" in canonical else 0.85,
                    )
                )
    # Retain different semantic types (e.g. handle within URL) with exact provenance.
    return list({(c.type, c.start, c.end, str(c.normalized)): c for c in out}.values())
