"""The article extractor consumes captured bytes without network or model calls."""

import importlib

import pytest


def test_article_text_excludes_navigation_and_scripts():
    extractor = importlib.import_module("darknetra.integrations.public_text")
    paragraph = "SYNTHETIC documentation explains how immutable evidence retains its provenance. "
    data = (
        "<html><head><title>SYNTHETIC article</title></head><body>"
        "<nav>SYNTHETIC navigation links</nav><script>alert('SYNTHETIC script')</script>"
        f"<main><article><h1>SYNTHETIC article</h1><p>{paragraph * 8}</p></article></main>"
        "</body></html>"
    ).encode()
    text = extractor.extract_public_text(data)
    assert "SYNTHETIC documentation explains" in text
    assert "navigation links" not in text
    assert "alert(" not in text


def test_article_text_is_bounded():
    extractor = importlib.import_module("darknetra.integrations.public_text")
    data = (
        "<html><body><article><p>"
        + "SYNTHETIC useful article content. " * 100
        + "</p></article></body></html>"
    ).encode()
    text = extractor.extract_public_text(data, max_chars=50)
    assert text
    assert len(text) <= 50


def test_oversized_input_is_rejected_before_extraction():
    extractor = importlib.import_module("darknetra.integrations.public_text")
    with pytest.raises(ValueError, match="2 MiB"):
        extractor.extract_public_text(b"x" * (2 * 1024 * 1024 + 1))
