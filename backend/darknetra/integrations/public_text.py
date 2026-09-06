"""Deterministic article extraction from captured HTML; no downloader or crawler."""

import trafilatura


def extract_public_text(data: bytes, *, max_chars: int = 12000) -> str | None:
    """Return bounded main text; callers must persist source bytes before calling."""
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("HTML exceeds the 2 MiB extraction limit")
    if not 1 <= max_chars <= 12000:
        raise ValueError("max_chars must be between 1 and 12000")
    text = trafilatura.extract(
        data,
        output_format="txt",
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    return text[:max_chars] if text else None
