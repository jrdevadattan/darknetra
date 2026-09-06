import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime

from pypdf import PdfReader

from darknetra.reports.model import ReportModel, Section
from darknetra.reports.redact import redact
from darknetra.reports.render import pack


def snapshot():
    return ReportModel(
        case_id="SYNTHETIC_CASE",
        case_code="SYNTHETIC-TEST",
        title="SYNTHETIC report",
        report_id="synthetic-report",
        version=1,
        generated_at=datetime(2026, 9, 6, tzinfo=UTC),
        generated_by="SYNTHETIC Analyst",
        synthetic=True,
        sections=[
            Section(
                key="observations",
                title="Observations",
                rows=[
                    {"text": "A synthetic observation was stored.", "evidence_codes": ["E-0001"]}
                ],
            )
        ],
        evidence_manifest=[{"code": "E-0001", "sha256": "a" * 64}],
        graph={"nodes": [], "edges": []},
        claims=[],
        dropped=[],
        redacted=True,
    )


def test_real_pdf_zip_manifest_and_deterministic_bytes():
    model = snapshot()
    files, zipped = pack(model)
    assert files["pack.pdf"].startswith(b"%PDF-")
    pdf = PdfReader(io.BytesIO(files["pack.pdf"]))
    assert "SYNTHETIC" in pdf.pages[0].extract_text()
    assert "E-0001" in "".join(p.extract_text() for p in pdf.pages)
    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        for artifact in manifest["artifacts"]:
            content = archive.read(artifact["name"])
            assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
        assert (
            archive.read("manifest.sha256")
            .decode()
            .startswith(hashlib.sha256(archive.read("manifest.json")).hexdigest())
        )
    assert pack(model)[1] == zipped


def test_redaction_in_nested_spans_and_authority():
    original = {
        "authority_reference": "SYNTHETIC AUTHORITY",
        "rows": [{"raw": "+91 9876543210 synthetic@example.invalid https://synthetic.invalid/a"}],
        "sha256": "a" * 64,
    }
    masked = redact(original)
    assert masked["authority_reference"] == "[withheld]"
    assert "9876543210" not in masked["rows"][0]["raw"]
    assert "synthetic@example.invalid" not in masked["rows"][0]["raw"]
    assert "https://" not in masked["rows"][0]["raw"]
    assert masked["sha256"] == original["sha256"]
    assert original["authority_reference"] == "SYNTHETIC AUTHORITY"
