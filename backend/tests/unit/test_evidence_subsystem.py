import io
import zipfile
from uuid import uuid4

import base58
import pytest
from hypothesis import given
from hypothesis import strategies as st

from darknetra.errors import TooLarge
from darknetra.evidence.vault import LocalVault
from darknetra.extract.normalize import normalize, raw_span
from darknetra.extract.validators import find_candidates, find_crypto
from darknetra.ingest.dispatch import parse
from darknetra.ingest.sniff import quarantine_reason, sniff
from darknetra.ingest.zipsafe import ZipUnsafe, safe_members
from darknetra.rag.chunker import chunk_text


@given(st.text(max_size=300))
def test_normalized_offsets_are_monotonic_and_bounded(raw):
    nt = normalize(raw)
    assert len(nt.to_raw) == len(nt.normalized) + 1
    assert list(nt.to_raw) == sorted(nt.to_raw)
    assert all(0 <= start <= len(raw) for start in nt.to_raw)
    assert all(nt.to_raw[i] < nt.ends[i] <= len(raw) for i in range(len(nt.normalized)))
    if nt.normalized:
        start, end = raw_span(nt, 0, len(nt.normalized))
        assert 0 <= start < end <= len(raw)


def test_hangul_and_combining_span_mapping():
    raw = "SYNTHETIC 각 e\u0301"
    nt = normalize(raw)
    assert "각" in nt.normalized and "é" in nt.normalized
    at = nt.normalized.index("각")
    start, end = raw_span(nt, at, at + 1)
    assert raw[start:end] == "각"


@pytest.mark.parametrize(
    "name",
    [
        "/absolute.txt",
        "C:/drive.txt",
        "\\\\server\\share.txt",
        "nested/../../escape.txt",
        "nested/archive.zip",
    ],
)
def test_zip_unsafe_paths_and_nested_archives(name):
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr(name, "SYNTHETIC")
    with zipfile.ZipFile(content) as archive, pytest.raises(ZipUnsafe):
        safe_members(archive)


def test_zip_symlink_ratio_size_and_member_limits():
    import stat

    def archive_with(info, content, compression=zipfile.ZIP_STORED):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=compression) as archive:
            archive.writestr(info, content)
        return zipfile.ZipFile(stream)

    member = zipfile.ZipInfo("SYNTHETIC-link")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with archive_with(member, "SYNTHETIC-target") as archive, pytest.raises(ZipUnsafe):
        safe_members(archive)
    with (
        archive_with("SYNTHETIC-ratio.txt", "A" * 100000, zipfile.ZIP_DEFLATED) as archive,
        pytest.raises(ZipUnsafe),
    ):
        safe_members(archive)
    with archive_with("SYNTHETIC-size.txt", "SYNTHETIC") as archive, pytest.raises(ZipUnsafe):
        safe_members(archive, max_bytes=2)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for number in range(2001):
            archive.writestr(f"SYNTHETIC-{number}", "")
    with zipfile.ZipFile(stream) as archive, pytest.raises(ZipUnsafe):
        safe_members(archive)


def test_image_parser_preserves_dimensions_and_rejects_large_side():
    from PIL import Image

    image = io.BytesIO()
    Image.new("RGB", (30, 20), "white").save(image, "PNG")
    derivatives, notices = parse(image.getvalue(), "IMAGE", "SYNTHETIC.png")
    assert dict(derivatives)["IMAGE_META"]["width"] == 30
    assert "OCR_UNAVAILABLE" in notices
    image = io.BytesIO()
    Image.new("RGB", (12001, 1), "white").save(image, "PNG")
    with pytest.raises(ValueError, match="IMAGE_SIZE_LIMIT"):
        parse(image.getvalue(), "IMAGE", "SYNTHETIC.png")


def test_csv_formulas_are_text_and_invalid_json_is_rejected():
    derivatives, notices = parse(b"label,value\nSYNTHETIC,=1+1\n", "CSV", "SYNTHETIC.csv")
    assert dict(derivatives)["ROWS"]["rows"][0][1] == "=1+1"
    assert "FORMULA_STORED_AS_TEXT" in notices
    import json

    with pytest.raises(json.JSONDecodeError):
        parse(b'{"SYNTHETIC":', "JSON", "SYNTHETIC.json")


def test_price_range_has_two_anchored_amounts():
    text = "SYNTHETIC INR 1500-2000"
    prices = [candidate for candidate in find_candidates(text) if candidate.type == "PRICE"]
    assert [candidate.normalized["amount"] for candidate in prices] == [1500, 2000]
    assert all(
        candidate.meta["range"] and text[candidate.start : candidate.end] == candidate.raw
        for candidate in prices
    )


def test_encrypted_pdf_degrades_without_reading_text():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("SYNTHETIC PASSWORD")
    stream = io.BytesIO()
    writer.write(stream)
    derivatives, notices = parse(stream.getvalue(), "PDF", "SYNTHETIC.pdf")
    assert derivatives == [] and notices == ["ENCRYPTED"]


async def test_stream_aborts_before_writing_excess(tmp_path):
    vault = LocalVault(tmp_path)

    async def stream():
        yield b"abc"
        yield b"def"
        pytest.fail("Read past rejected chunk")

    with pytest.raises(TooLarge):
        await vault.put_stream(stream(), max_bytes=4)
    assert not list(tmp_path.iterdir())


async def test_vault_duplicate_and_path_safety(tmp_path):
    vault = LocalVault(tmp_path)
    case = uuid4()
    key = await vault.put_bytes(case, b"SYNTHETIC")
    assert await vault.put_bytes(case, b"SYNTHETIC") == key
    with pytest.raises(ValueError):
        vault.path_for("../../outside")


def test_archive_and_script_safety():
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("../escape.txt", "SYNTHETIC")
    with zipfile.ZipFile(content) as archive, pytest.raises(ZipUnsafe):
        safe_members(archive)
    assert quarantine_reason(sniff(b"SYNTHETIC", "sample.ps1"), "sample.ps1", "UPLOAD")
    assert sniff(content.getvalue(), "sample.jpg").ext_mismatch


def test_html_has_no_active_content():
    result, _ = parse(
        b'<html><script>danger</script><iframe src="x"></iframe><p onclick="x">SYNTHETIC visible</p><a href="https://example.invalid">link</a></html>',
        "HTML",
        "sample.html",
    )
    docs = dict(result)
    assert "danger" not in docs["TEXT"]["text"]
    assert "onclick" not in docs["HTML_SAFE"]["html"]
    assert "example.invalid" not in docs["HTML_SAFE"]["html"]


def test_normalization_maps_combining_unicode_and_zero_width():
    raw = "SYNTHETIC\r\n cafe\u0301\t  ਚਿੱਟਾ\u200b maal"
    nt = normalize(raw)
    start = nt.normalized.index("café")
    a, b = raw_span(nt, start, start + 4)
    assert raw[a:b] == "cafe\u0301"
    assert len(nt.to_raw) == len(nt.normalized) + 1
    assert "\r" not in nt.normalized and "\u200b" not in nt.normalized


def test_chunk_exact_spans_and_bounded_windows():
    text = "SYNTHETIC " + "ਚਿੱਟਾ maal. " * 700 + "\n\nEND"
    drafts = chunk_text(text)
    assert len(drafts) > 2
    assert all(text[d.span_start : d.span_end] == d.text and len(d.text) <= 1200 for d in drafts)


def test_valid_testnet_wallet_and_mutation():
    address = base58.b58encode_check(bytes([111]) + bytes(range(20))).decode()
    assert find_crypto(address)[0].valid
    mutated = address[:-1] + ("1" if address[-1] != "1" else "2")
    assert not find_crypto(mutated)[0].valid


def test_commerce_and_negative_numbers():
    candidates = find_candidates("SYNTHETIC ₹2,500 2 tola 12/05/2026 10:30 5 min 2 km")
    assert [c.normalized for c in candidates if c.type == "PRICE"] == [
        {"amount": 2500.0, "currency": "INR"}
    ]
    assert len([c for c in candidates if c.type == "QUANTITY"]) == 1
    assert all(
        c.raw == "SYNTHETIC ₹2,500 2 tola 12/05/2026 10:30 5 min 2 km"[c.start : c.end]
        for c in candidates
    )


def test_telegram_parts_and_whatsapp_continuation():
    data = b'{"messages":[{"id":1,"type":"message","text":["SYNTHETIC ",{"type":"bold","text":"maal"}]}]}'
    result, _ = parse(data, "JSON", "result.json")
    assert dict(result)["MESSAGES"]["messages"][0]["text"] == "SYNTHETIC maal"
    result, _ = parse(b"1/9/2026, 10:30 - SYNTHETIC: first\ncontinued", "TEXT", "chat.txt")
    assert dict(result)["MESSAGES"]["messages"][0]["text"] == "first\ncontinued"


def test_bech32_checksum_and_pgp_fingerprint_mismatch():
    import pgpy
    from bech32 import bech32_encode, convertbits
    from pgpy.constants import PubKeyAlgorithm

    from darknetra.extract.validators import find_pgp

    address = bech32_encode("tb", [0] + convertbits(list(bytes(range(20))), 8, 5))
    candidates = find_crypto(address)
    assert candidates[0].valid and candidates[0].meta["network"] == "testnet"
    assert not find_crypto(address[:-1] + ("q" if address[-1] != "q" else "p"))[0].valid
    # In-memory test key only; never serialize or persist its private component.
    private = pgpy.PGPKey.new(PubKeyAlgorithm.RSAEncryptOrSign, 1024)
    public = str(private.pubkey)
    candidates = find_pgp(public + "\nClaimed fingerprint: " + "ABCD " * 9 + "ABCD")
    assert any(c.validator == "pgpy_computed" and c.valid for c in candidates)
    assert any(c.meta.get("mismatch") for c in candidates)


def test_synthetic_bundle_has_separate_items_and_no_private_key(tmp_path):
    import importlib.util
    import json
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "synthetic_generator", Path(__file__).resolve().parents[3] / "data/synthetic/generator.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module.generate(tmp_path)
    assert len(manifest["files"]) >= 9
    assert all(item["source_class"] == "SYNTHETIC" for item in manifest["files"])
    families = {item["filename"]: item["source_family"] for item in manifest["files"]}
    assert families["telegram/result.json"] != families["listings/SYNTHETIC_ALIAS_A.html"]
    assert (
        families["listings/SYNTHETIC_ALIAS_A.html"] != families["listings/SYNTHETIC_ALIAS_B.html"]
    )
    publisher = (tmp_path / "listings/SYNTHETIC_ALIAS_A.html").read_text()
    assert "Vendor alias: SYNTHETIC_ALIAS_A" in publisher
    assert (tmp_path / "listings/SYNTHETIC_ALIAS_A_profile.html").exists()
    assert (tmp_path / "listings/SYNTHETIC_ALIAS_A_CHAT_profile.html").exists()
    for key in tmp_path.glob("keys/*.asc"):
        assert "PRIVATE KEY" not in key.read_text()
    with zipfile.ZipFile(tmp_path / "bundle.zip") as archive:
        assert "ground_truth.json" not in archive.namelist()
        safe_members(archive)
    truth = json.loads((tmp_path / "ground_truth.json").read_text())
    assert truth["trend"]["first_day"] == 5 and truth["aliases"]["decoy_pairs"]
