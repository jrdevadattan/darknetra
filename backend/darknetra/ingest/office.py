"""Bounded, passive OOXML text extraction without archive extraction or evaluation."""

import io
import posixpath
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree

from darknetra.ingest.zipsafe import ZipUnsafe, safe_members

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_MEMBER_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 5_000_000
_ROOTS = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml", ".pptx": "ppt/presentation.xml"}
_ACTIVE_SUFFIXES = ("vbaproject.bin", ".exe", ".dll", ".js", ".vbs", ".ps1", ".jar", ".apk", ".msi")
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


class OfficeUnsafe(ValueError):
    pass


class _Budget:
    def __init__(self) -> None:
        self.size = 0

    def add(self, value: str) -> str:
        self.size += len(value)
        if self.size > MAX_TEXT_CHARS:
            raise OfficeUnsafe("OFFICE_TEXT_LIMIT")
        return value


def _normal_names(archive: zipfile.ZipFile) -> set[str]:
    members = safe_members(archive, MAX_ARCHIVE_BYTES)
    names = [member.filename.replace("\\", "/") for member in members]
    if len(names) != len(set(names)):
        raise OfficeUnsafe("OFFICE_DUPLICATE_MEMBER")
    lower = {name.lower() for name in names}
    if any(
        name.endswith(_ACTIVE_SUFFIXES) or "/embeddings/" in name or "/activex/" in name
        for name in lower
    ):
        raise OfficeUnsafe("OFFICE_ACTIVE_CONTENT")
    if any(member.flag_bits & 1 for member in members):
        raise OfficeUnsafe("OFFICE_ENCRYPTED")
    return set(names)


def inspect_office(data: bytes, ext: str) -> tuple[bool, str | None]:
    expected = _ROOTS.get(ext)
    if expected is None or not data.startswith(b"PK"):
        return False, None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            raw_names = {item.filename.replace("\\", "/") for item in archive.infolist()}
            if "[Content_Types].xml" not in raw_names or expected not in raw_names:
                return False, None
            try:
                _normal_names(archive)
            except (OfficeUnsafe, ZipUnsafe) as exc:
                return True, str(exc)
    except zipfile.BadZipFile:
        return True, "OFFICE_UNSAFE_ARCHIVE"
    return True, None


def _xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    info = archive.getinfo(name)
    if info.file_size > MAX_MEMBER_BYTES:
        raise OfficeUnsafe("OFFICE_MEMBER_LIMIT")
    data = archive.read(info)
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            encoding = "utf-16"
        elif data.startswith(b"<\x00"):
            encoding = "utf-16-le"
        elif data.startswith(b"\x00<"):
            encoding = "utf-16-be"
        else:
            sample = data[:128]
            even_nuls = sample[::2].count(0)
            odd_nuls = sample[1::2].count(0)
            encoding = (
                "utf-16-le"
                if odd_nuls > len(sample) // 8
                else "utf-16-be"
                if even_nuls > len(sample) // 8
                else "utf-8-sig"
            )
        declaration_text = data.decode(encoding)
    except UnicodeDecodeError as exc:
        raise OfficeUnsafe("OFFICE_INVALID_XML_ENCODING") from exc
    if "\x00" in declaration_text:
        raise OfficeUnsafe("OFFICE_INVALID_XML_ENCODING")
    if re.search(r"<!DOCTYPE|<!ENTITY", declaration_text, re.IGNORECASE):
        raise OfficeUnsafe("OFFICE_XML_ENTITY")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise OfficeUnsafe("OFFICE_INVALID_XML") from exc


def _local(node: ElementTree.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _text_nodes(root: ElementTree.Element, budget: _Budget) -> str:
    return "".join(
        budget.add(node.text) for node in root.iter() if _local(node) == "t" and node.text
    )


def _relationships(
    archive: zipfile.ZipFile, rels_name: str, source_name: str, names: set[str]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for rel in _xml(archive, rels_name):
        if _local(rel) != "Relationship":
            continue
        rid, target = rel.attrib.get("Id"), rel.attrib.get("Target")
        if not rid or not target or rid in result or rel.attrib.get("TargetMode") == "External":
            raise OfficeUnsafe("OFFICE_INVALID_RELATIONSHIP")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source_name), target))
        if resolved.startswith("../") or resolved not in names:
            raise OfficeUnsafe("OFFICE_INVALID_RELATIONSHIP")
        result[rid] = resolved
    return result


def _join_units(units: list[list[str]], budget: _Budget) -> tuple[str, list[tuple[int, int]]]:
    output: list[str] = []
    spans: list[tuple[int, int]] = []
    position = 0
    for index, unit in enumerate(units):
        if index:
            separator = budget.add("\n")
            output.append(separator)
            position += len(separator)
        budget.add("\n" * max(0, len(unit) - 1))
        value = "\n".join(unit)
        start = position
        output.append(value)
        position += len(value)
        spans.append((start, position))
    text = "".join(output)
    source_map = []
    for start, end in spans:
        start_line = text.count("\n", 0, start)
        value = text[start:end]
        source_map.append((start_line, start_line + (value.count("\n") + 1 if value else 0)))
    return text, source_map


def _docx(archive: zipfile.ZipFile, budget: _Budget) -> dict:
    paragraphs: list[str] = []
    for paragraph in _xml(archive, "word/document.xml").iter():
        if _local(paragraph) != "p":
            continue
        parts: list[str] = []
        for node in paragraph.iter():
            kind = _local(node)
            if kind == "t" and node.text:
                parts.append(budget.add(node.text))
            elif kind == "tab":
                parts.append(budget.add("\t"))
            elif kind in {"br", "cr"}:
                parts.append(budget.add("\n"))
        if value := "".join(parts):
            paragraphs.append(value)
    budget.add("\n" * max(0, len(paragraphs) - 1))
    return _text_doc("\n".join(paragraphs), None)


def _xlsx(archive: zipfile.ZipFile, names: set[str], budget: _Budget) -> dict:
    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        for item in _xml(archive, "xl/sharedStrings.xml").iter():
            if _local(item) == "si":
                shared.append(_text_nodes(item, budget))
    rels = _relationships(archive, "xl/_rels/workbook.xml.rels", "xl/workbook.xml", names)
    parts: list[str] = []
    for sheet in _xml(archive, "xl/workbook.xml").iter():
        if _local(sheet) == "sheet":
            rid = sheet.attrib.get(f"{{{_REL}}}id")
            if not rid or rid not in rels:
                raise OfficeUnsafe("OFFICE_INVALID_RELATIONSHIP")
            parts.append(rels[rid])
    units: list[list[str]] = []
    for name in parts:
        rows: list[str] = []
        for row in _xml(archive, name).iter():
            if _local(row) != "row":
                continue
            values: list[str] = []
            for cell in row:
                if _local(cell) != "c":
                    continue
                kind = cell.attrib.get("t")
                raw = next((node.text or "" for node in cell if _local(node) == "v"), "")
                if kind == "s":
                    if not raw.isdigit() or int(raw) >= len(shared):
                        raise OfficeUnsafe("OFFICE_INVALID_SHARED_STRING")
                    raw = budget.add(shared[int(raw)])
                elif kind == "inlineStr":
                    raw = _text_nodes(cell, budget)
                else:
                    raw = budget.add(raw)
                values.append(raw)
            if values:
                budget.add("\t" * max(0, len(values) - 1))
                rows.append("\t".join(values))
        units.append(rows)
    text, source_map = _join_units(units, budget)
    return _text_doc(text, source_map)


def _pptx(archive: zipfile.ZipFile, names: set[str], budget: _Budget) -> dict:
    rels = _relationships(archive, "ppt/_rels/presentation.xml.rels", "ppt/presentation.xml", names)
    parts: list[str] = []
    for slide in _xml(archive, "ppt/presentation.xml").iter():
        if _local(slide) == "sldId":
            rid = slide.attrib.get(f"{{{_REL}}}id")
            if not rid or rid not in rels:
                raise OfficeUnsafe("OFFICE_INVALID_RELATIONSHIP")
            parts.append(rels[rid])
    units: list[list[str]] = []
    for name in parts:
        root = _xml(archive, name)
        paragraphs: list[str] = []
        for paragraph in root.iter():
            if _local(paragraph) == "p":
                value = _text_nodes(paragraph, budget)
                if value:
                    paragraphs.append(value)
        if not paragraphs:
            value = _text_nodes(root, budget)
            if value:
                paragraphs.append(value)
        units.append(paragraphs)
    text, source_map = _join_units(units, budget)
    return _text_doc(text, source_map)


def _text_doc(text: str, page_map: list[tuple[int, int]] | None) -> dict:
    return {
        "text": text,
        "line_offsets": [0] + [m.end() for m in re.finditer("\n", text)],
        "page_map": page_map,
        "contexts": [],
    }


def parse_office(data: bytes, filename: str) -> tuple[list[tuple[str, dict]], list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = _normal_names(archive)
            ext = PurePosixPath(filename).suffix.lower()
            expected = _ROOTS.get(ext)
            if not expected or "[Content_Types].xml" not in names or expected not in names:
                raise OfficeUnsafe("OFFICE_CONTENT_MISMATCH")
            budget = _Budget()
            document = (
                _docx(archive, budget)
                if ext == ".docx"
                else _xlsx(archive, names, budget)
                if ext == ".xlsx"
                else _pptx(archive, names, budget)
            )
    except (zipfile.BadZipFile, KeyError, ZipUnsafe) as exc:
        raise OfficeUnsafe("OFFICE_UNSAFE_ARCHIVE") from exc
    return ([("TEXT", document)], []) if document["text"] else ([], ["TEXT_NOT_AVAILABLE"])
