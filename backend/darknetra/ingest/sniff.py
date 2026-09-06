from dataclasses import dataclass
from pathlib import Path

import filetype


@dataclass(frozen=True)
class Sniffed:
    mime: str
    kind: str
    ext_mismatch: bool = False


def decode(data: bytes) -> str:
    return data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")


def sniff(data: bytes, filename: str) -> Sniffed:
    ext = Path(filename).suffix.lower()
    guessed = filetype.guess(data)
    if guessed:
        mime = guessed.mime
        kind = (
            "IMAGE"
            if mime.startswith("image/")
            else "AUDIO"
            if mime.startswith("audio/")
            else "VIDEO"
            if mime.startswith("video/")
            else {"application/pdf": "PDF", "application/zip": "ZIP"}.get(mime, "UNKNOWN")
        )
        if ext in {".docx", ".xlsx", ".pptx"}:
            kind = "OFFICE"
        return Sniffed(
            mime,
            kind,
            ext.lstrip(".")
            not in {guessed.extension, "jpeg" if guessed.extension == "jpg" else guessed.extension},
        )
    try:
        text = decode(data)
    except UnicodeError:
        return Sniffed("application/octet-stream", "UNKNOWN")
    if sum(ord(c) < 32 and c not in "\t\r\n\f" for c in text) > len(text) * 0.05:
        return Sniffed("application/octet-stream", "UNKNOWN")
    stripped = text.lstrip().lower()
    if stripped.startswith(("<!doctype html", "<html", "<body")):
        return Sniffed("text/html", "HTML")
    if stripped.startswith("warc/"):
        return Sniffed("application/warc", "WARC")
    if stripped.startswith(("{", "[")):
        return Sniffed("application/json", "JSON")
    if ext == ".csv":
        return Sniffed("text/csv", "CSV")
    return Sniffed("text/plain", "TEXT")


def quarantine_reason(sniffed, filename, source_class):
    if Path(filename).suffix.lower() in {
        ".js",
        ".vbs",
        ".ps1",
        ".sh",
        ".bat",
        ".cmd",
        ".py",
        ".jar",
        ".apk",
        ".msi",
        ".exe",
        ".com",
        ".dll",
    }:
        return "UNSAFE_EXECUTABLE_OR_SCRIPT"
    if sniffed.kind in {"UNKNOWN", "OFFICE", "VIDEO"}:
        return "UNSUPPORTED_UNSAFE_TYPE"
    if sniffed.kind == "IMAGE" and source_class == "OSINT_DARK":
        return "DARK_IMAGE_REVIEW_REQUIRED"
    return None
