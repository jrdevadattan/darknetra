import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    text: str
    span_start: int
    span_end: int
    line_no: int
    lang: str
    script: str
    kind: str


def chunk_text(text: str, *, limit=1200, overlap=150):
    if limit <= overlap or overlap < 0:
        raise ValueError("Invalid chunk window")
    chunks = []
    for paragraph in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text):
        start, stop = paragraph.span()
        while start < stop:
            end = min(start + limit, stop)
            if end < stop:
                breaks = list(re.finditer(r"[.!?।\n]", text[start + limit // 2 : end]))
                if breaks:
                    end = start + limit // 2 + breaks[-1].end()
            raw = text[start:end]
            script = (
                "Guru"
                if any("\u0a00" <= c <= "\u0a7f" for c in raw)
                else "Deva"
                if any("\u0900" <= c <= "\u097f" for c in raw)
                else "Latn"
            )
            chunks.append(
                ChunkDraft(
                    len(chunks),
                    raw,
                    start,
                    end,
                    text.count("\n", 0, start) + 1,
                    {"Guru": "pa", "Deva": "hi", "Latn": "und"}[script],
                    script,
                    "paragraph",
                )
            )
            if end == stop:
                break
            start = max(start + 1, end - overlap)
    return chunks
