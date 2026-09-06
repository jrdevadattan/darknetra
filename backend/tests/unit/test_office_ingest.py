"""SYNTHETIC passive OOXML and PDF provenance tests."""

import io
import zipfile

import pytest
from fpdf import FPDF

import darknetra.ingest.office as office
from darknetra.ingest.dispatch import parse
from darknetra.ingest.office import OfficeUnsafe
from darknetra.ingest.sniff import quarantine_reason, sniff


def package(files: dict[str, str | bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        for name, value in files.items():
            archive.writestr(name, value)
    return stream.getvalue()


def test_docx_is_content_validated_and_parsed_without_invented_pages():
    data = package(
        {
            "word/document.xml": """<w:document xmlns:w="urn:w"><w:body>
            <w:p><w:r><w:t>SYNTHETIC first</w:t></w:r></w:p>
            <w:p><w:r><w:t>SYNTHETIC</w:t></w:r><w:tab/><w:r><w:t>second</w:t></w:r><w:br/><w:r><w:t>line</w:t></w:r></w:p>
            </w:body></w:document>"""
        }
    )
    detected = sniff(data, "SYNTHETIC.docx")
    assert detected.kind == "OFFICE"
    assert quarantine_reason(detected, "SYNTHETIC.docx", "SYNTHETIC") is None
    document = dict(parse(data, detected.kind, "SYNTHETIC.docx")[0])["TEXT"]
    assert document["text"] == "SYNTHETIC first\nSYNTHETIC\tsecond\nline"
    assert document["page_map"] is None
    assert document["line_offsets"] == [0, 16, 33]


def test_xlsx_preserves_sheet_line_ranges_and_never_evaluates_formula():
    data = package(
        {
            "xl/workbook.xml": '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="two" r:id="r2"/><sheet name="one" r:id="r1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Target="worksheets/sheet2.xml"/></Relationships>',
            "xl/sharedStrings.xml": '<sst xmlns="urn:x"><si><t>SYNTHETIC</t></si></sst>',
            "xl/worksheets/sheet1.xml": '<worksheet xmlns="urn:x"><sheetData><row><c t="s"><v>0</v></c><c><f>1+1</f><v>2</v></c></row></sheetData></worksheet>',
            "xl/worksheets/sheet2.xml": '<worksheet xmlns="urn:x"><sheetData><row><c t="inlineStr"><is><t>SYNTHETIC TWO</t></is></c></row></sheetData></worksheet>',
        }
    )
    document = dict(parse(data, "OFFICE", "SYNTHETIC.xlsx")[0])["TEXT"]
    assert document["text"] == "SYNTHETIC TWO\nSYNTHETIC\t2"
    assert "1+1" not in document["text"]
    assert document["page_map"] == [(0, 1), (1, 2)]


def test_pptx_preserves_relationship_slide_order_and_line_ranges():
    data = package(
        {
            "ppt/presentation.xml": '<p:presentation xmlns:p="urn:p" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId r:id="r10"/><p:sldId r:id="r2"/></p:sldIdLst></p:presentation>',
            "ppt/_rels/presentation.xml.rels": '<Relationships><Relationship Id="r2" Target="slides/slide2.xml"/><Relationship Id="r10" Target="slides/slide10.xml"/></Relationships>',
            "ppt/slides/slide10.xml": '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:t>SYNTHETIC ten</a:t></p:sld>',
            "ppt/slides/slide2.xml": '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:t>SYNTHETIC two</a:t></p:sld>',
        }
    )
    document = dict(parse(data, "OFFICE", "SYNTHETIC.pptx")[0])["TEXT"]
    assert document["text"] == "SYNTHETIC ten\nSYNTHETIC two"
    assert document["page_map"] == [(0, 1), (1, 2)]


def test_active_content_is_quarantined_and_entities_are_rejected():
    active = package({"word/document.xml": "<document/>", "word/vbaProject.bin": b"SYNTHETIC"})
    detected = sniff(active, "SYNTHETIC.docx")
    assert quarantine_reason(detected, "SYNTHETIC.docx", "SYNTHETIC") == "OFFICE_ACTIVE_CONTENT"
    entity = package(
        {"word/document.xml": '<!DOCTYPE x [<!ENTITY e "SYNTHETIC">]><document>&e;</document>'}
    )
    with pytest.raises(OfficeUnsafe, match="OFFICE_XML_ENTITY"):
        parse(entity, "OFFICE", "SYNTHETIC.docx")
    utf16 = '<?xml version="1.0"?><!DOCTYPE x><document/>'.encode("utf-16")
    with pytest.raises(OfficeUnsafe, match="OFFICE_XML_ENTITY"):
        parse(package({"word/document.xml": utf16}), "OFFICE", "SYNTHETIC.docx")
    utf16_no_bom = '  <?xml version="1.0"?><!DOCTYPE x><document/>'.encode("utf-16-le")
    with pytest.raises(OfficeUnsafe, match="OFFICE_XML_ENTITY"):
        parse(package({"word/document.xml": utf16_no_bom}), "OFFICE", "SYNTHETIC.docx")
    with pytest.raises(OfficeUnsafe, match="OFFICE_ACTIVE_CONTENT"):
        parse(active, "OFFICE", "SYNTHETIC.docx")


def test_extension_alone_does_not_make_plain_zip_an_office_document():
    data = package({"SYNTHETIC.txt": "SYNTHETIC"})
    assert sniff(data, "SYNTHETIC.docx").kind == "ZIP"


def test_xlsx_multiline_cells_three_columns_and_rows_have_exact_map():
    data = package(
        {
            "xl/workbook.xml": '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="SYNTHETIC" r:id="r1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
            "xl/worksheets/sheet1.xml": '<worksheet><row><c t="inlineStr"><is><t>A\nA2</t></is></c><c><v>B</v></c><c><v>C</v></c></row><row><c><v>D</v></c><c><v>E</v></c><c><v>F</v></c></row></worksheet>',
        }
    )
    document = dict(parse(data, "OFFICE", "SYNTHETIC.xlsx")[0])["TEXT"]
    assert document["text"] == "A\nA2\tB\tC\nD\tE\tF"
    assert document["page_map"] == [(0, 3)]
    assert document["line_offsets"] == [0, 2, 9]


def test_duplicate_members_and_repeated_shared_string_budget_are_rejected(monkeypatch):
    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
        archive.writestr("word/document.xml", "<document/>")
    with pytest.raises(OfficeUnsafe, match="OFFICE_DUPLICATE_MEMBER"):
        parse(duplicate.getvalue(), "OFFICE", "SYNTHETIC.docx")

    monkeypatch.setattr(office, "MAX_TEXT_CHARS", 20)
    repeated = package(
        {
            "xl/workbook.xml": '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheet r:id="r1"/></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
            "xl/sharedStrings.xml": "<sst><si><t>SYNTHETIC</t></si></sst>",
            "xl/worksheets/sheet1.xml": '<worksheet><row><c t="s"><v>0</v></c><c t="s"><v>0</v></c><c t="s"><v>0</v></c></row></worksheet>',
        }
    )
    with pytest.raises(OfficeUnsafe, match="OFFICE_TEXT_LIMIT"):
        parse(repeated, "OFFICE", "SYNTHETIC.xlsx")


def test_pdf_page_map_uses_exact_page_line_intervals():
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    pdf.add_page()
    pdf.multi_cell(0, 10, "SYNTHETIC first\nSYNTHETIC second")
    pdf.add_page()
    pdf.add_page()
    pdf.cell(0, 10, "SYNTHETIC third")
    derivatives, notices = parse(bytes(pdf.output()), "PDF", "SYNTHETIC.pdf")
    document = dict(derivatives)["TEXT"]
    assert notices == []
    assert document["page_map"] == [(0, 2), (3, 3), (5, 6)]
    offsets = document["line_offsets"] + [len(document["text"])]
    lines = [
        document["text"][offsets[i] : offsets[i + 1]].rstrip("\n") for i in range(len(offsets) - 1)
    ]
    reconstructed = ["\n".join(lines[start:end]) for start, end in document["page_map"]]
    assert reconstructed == ["SYNTHETIC first\nSYNTHETIC second", "", "SYNTHETIC third"]
