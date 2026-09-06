"""Deterministic UTF-8, HTML, PDF, and ZIP artifacts with detached hashes."""

import hashlib
import io
import json
import textwrap
import zipfile
from pathlib import Path

from fpdf import FPDF
from jinja2 import Environment, StrictUndefined
from markdown_it import MarkdownIt

TEMPLATE = """# Investigation pack — {{ model.case_code }}

{% if model.synthetic %}**SYNTHETIC DEMO — generated test material**
{% endif %}
{{ model.title }}

Report {{ model.report_id }} · Version {{ model.version }}
Generated {{ model.generated_at.isoformat() }} by {{ model.generated_by }}
Redacted: {{ model.redacted }}

Integrity: verify each artifact against `manifest.json`; verify that manifest with
`manifest.sha256`. The ZIP SHA-256 is supplied as a detached download. No document
contains a claim to hash its own final bytes.

{% for section in model.sections %}
## {{ section.title }}

{% for row in section.rows %}
{% if row.get('text') %}{{ row.text }} {% for code in row.get('evidence_codes', []) %}[{{ code }}] {% endfor %}
{% else %}
```json
{{ row | tojson_pretty }}
```
{% endif %}
{% else %}No records in this snapshot.
{% endfor %}
{% endfor %}
"""


def to_markdown(model):
    env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    env.filters["tojson_pretty"] = lambda value: json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=2
    )
    return env.from_string(TEMPLATE).render(model=model)


def to_html(markdown):
    body = MarkdownIt("commonmark", {"html": False}).render(markdown)
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Investigation pack</title><style>body{font:15px/1.5 system-ui;max-width:1000px;margin:auto;padding:30px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:12px}h2{border-top:1px solid #aaa;padding-top:20px}@media print{h2{break-before:page}pre{break-inside:avoid}}@page{margin:18mm}</style><body>'
        + body
        + "</body></html>"
    )


def to_pdf(markdown, generated_at):
    pdf = FPDF()
    pdf.set_creation_date(generated_at)
    pdf.set_title("DARKNETRA evidence-backed investigation pack")
    pdf.set_author("DARKNETRA")
    pdf.set_auto_page_break(auto=True, margin=15)
    font = next(
        (
            path
            for path in [
                Path("C:/Windows/Fonts/Nirmala.ttf"),
                Path("C:/Windows/Fonts/arial.ttf"),
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            ]
            if path.is_file()
        ),
        None,
    )
    if font:
        pdf.add_font("Report", fname=str(font))
        pdf.set_font("Report", size=8)
    else:
        pdf.set_font("Helvetica", size=8)
        markdown = (
            "PDF font fallback: Unicode is escaped; UTF-8 originals are in pack.md and pack.html.\n\n"
            + markdown.encode("ascii", "backslashreplace").decode()
        )
    pdf.add_page()
    for line in markdown.splitlines():
        for part in textwrap.wrap(line, width=95, replace_whitespace=False) or [""]:
            pdf.cell(0, 4.5, text=part, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def canonical_json(value):
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, default=str) + "\n"
    ).encode()


def pack(model):
    markdown = to_markdown(model)
    files = {
        "pack.md": markdown.encode(),
        "pack.html": to_html(markdown).encode(),
        "pack.pdf": to_pdf(markdown, model.generated_at),
        "graph.json": canonical_json(model.graph),
    }
    manifest = {
        "schema_version": 1,
        "case_id": model.case_id,
        "case_code": model.case_code,
        "report_id": model.report_id,
        "version": model.version,
        "generated_at": model.generated_at.isoformat(),
        "synthetic": model.synthetic,
        "redacted": model.redacted,
        "evidence": model.evidence_manifest,
        "artifacts": [
            {"name": name, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
            for name, data in sorted(files.items())
        ],
        "claims": model.claims,
        "unverified_dropped": len(model.dropped),
    }
    files["manifest.json"] = canonical_json(manifest)
    files["manifest.sha256"] = (
        hashlib.sha256(files["manifest.json"]).hexdigest() + "  manifest.json\n"
    ).encode()
    output = io.BytesIO()
    stamp = model.generated_at
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(
                name,
                (
                    max(1980, stamp.year),
                    stamp.month,
                    stamp.day,
                    stamp.hour,
                    stamp.minute,
                    stamp.second,
                ),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o444 << 16
            archive.writestr(info, data)
    return files, output.getvalue()
