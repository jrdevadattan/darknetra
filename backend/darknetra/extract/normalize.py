import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedText:
    raw: str
    normalized: str
    to_raw: tuple[int, ...]
    ends: tuple[int, ...]
    warnings: tuple[str, ...]


def normalize(raw: str) -> NormalizedText:
    chars, starts, ends = [], [], []
    i, removed = 0, 0
    while i < len(raw):
        start = i
        c = raw[i]
        i += 1
        if c in "\u200b\u200c\u200d\ufeff\u200e\u200f":
            removed += 1
            continue
        if c == "\r":
            if i < len(raw) and raw[i] == "\n":
                i += 1
            c = "\n"
        elif c in " \t":
            while i < len(raw) and raw[i] in " \t":
                i += 1
            c = " "
        else:
            while i < len(raw) and unicodedata.combining(raw[i]):
                c += raw[i]
                i += 1
            c = unicodedata.normalize("NFC", c)
            # Hangul Jamo compose despite having canonical combining class zero.
            while i < len(raw):
                combined = unicodedata.normalize("NFC", c + raw[i])
                if len(combined) >= len(c) + 1:
                    break
                c = combined
                i += 1
        for char in c:
            chars.append(char)
            starts.append(start)
            ends.append(i)
    return NormalizedText(
        raw,
        "".join(chars),
        tuple(starts + [len(raw)]),
        tuple(ends),
        (f"zero_width_removed:{removed}",) if removed else (),
    )


def raw_span(nt, start, end):
    if not 0 <= start < end <= len(nt.normalized):
        raise ValueError("Invalid normalized span")
    return nt.to_raw[start], nt.ends[end - 1]
