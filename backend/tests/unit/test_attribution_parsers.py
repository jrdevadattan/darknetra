"""Parser attribution must resolve to the precise text it describes."""

from darknetra.ingest.dispatch import parse


def test_whatsapp_context_preserves_raw_multiline_spans():
    raw = "1/9/2026, 10:30 PM - SYNTHETIC_A: SYNTHETIC first\ncontinued\n1/9/2026, 11:30 PM - SYNTHETIC_B: SYNTHETIC second"
    docs = dict(parse(raw.encode(), "TEXT", "chat.txt")[0])
    assert docs["TEXT"]["text"] == raw
    contexts = docs["TEXT"]["contexts"]
    assert [c["value"] for c in contexts] == ["SYNTHETIC_A", "SYNTHETIC_B"]
    assert contexts[0]["timestamp"] == "2026-09-01T22:30:00+05:30"
    for context in contexts:
        assert raw[context["start"] : context["end"]] == context["value"]
    first = contexts[0]["context_span"]
    assert "continued" in raw[first["start"] : first["end"]]
    assert "SYNTHETIC_B" not in raw[first["start"] : first["end"]]


def test_explicit_publisher_is_not_a_mentioned_alias():
    raw = b"<p>SYNTHETIC</p><pre>Vendor alias: SYNTHETIC_ALIAS_A\nSYNTHETIC_ALIAS_B is mentioned only.\nwickr:synthetic_a</pre>"
    docs = dict(parse(raw, "HTML", "listing.html")[0])
    text = docs["TEXT"]["text"]
    contexts = docs["TEXT"]["contexts"]
    assert len(contexts) == 1
    assert contexts[0]["value"] == "SYNTHETIC_ALIAS_A"
    assert contexts[0]["role"] == "publisher"
    assert contexts[0]["context_span"] == {"start": 0, "end": len(text)}


def test_explicit_publisher_timestamp_is_parsed_from_source_text():
    data = b"<pre>SYNTHETIC\nVendor alias: SYNTHETIC_ALIAS_A\nPublished at: 2026-09-01T10:00:00+00:00\nSYNTHETIC text</pre>"
    docs = dict(parse(data, "HTML", "synthetic.html")[0])
    assert docs["TEXT"]["contexts"][0]["timestamp"] == "2026-09-01T10:00:00+00:00"
