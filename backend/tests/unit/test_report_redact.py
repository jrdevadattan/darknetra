"""SYNTHETIC phone fixtures from metadata examples and fictional NANP numbers."""

import copy

import phonenumbers
import pytest

from darknetra.reports.redact import redact, text


def synthetic_indian_phone():
    return phonenumbers.example_number_for_type("IN", phonenumbers.PhoneNumberType.MOBILE)


@pytest.mark.parametrize("format", ["national", "national_digits", "international", "e164"])
def test_every_extraction_phone_format_is_redacted(format):
    number = synthetic_indian_phone()
    formats = {
        "national": phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.NATIONAL),
        "national_digits": str(number.national_number),
        "international": phonenumbers.format_number(
            number, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        ),
        "e164": phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164),
    }
    value = formats[format]
    original = f"SYNTHETIC contact {value}; keep this text."
    matches = list(phonenumbers.PhoneNumberMatcher(original, "IN"))
    assert len(matches) == 1
    result = text(original)
    assert value not in result
    assert str(number.national_number) not in result
    assert result.startswith("SYNTHETIC contact ") and result.endswith("; keep this text.")


def test_nested_observations_and_appendix_mask_all_match_spans_without_mutation():
    domestic = str(synthetic_indian_phone().national_number)
    international = "+1 202-555-0123"  # Reserved fictional NANP 555-0100..0199 range.
    original = {
        "source_class": "SYNTHETIC",
        "sections": [
            {
                "key": "observations",
                "rows": [{"raw": domestic, "normalized": {"value": "+91" + domestic}}],
            },
            {
                "key": "appendix",
                "rows": [
                    {
                        "excerpt": f"SYNTHETIC {domestic}, then {international}, and {domestic} again.",
                        "cited_spans": [{"text": domestic}, {"text": international}],
                    }
                ],
            },
        ],
    }
    before = copy.deepcopy(original)
    masked = redact(original)
    assert original == before
    observation = masked["sections"][0]["rows"][0]
    appendix = masked["sections"][1]["rows"][0]
    for value in [
        observation["raw"],
        observation["normalized"]["value"],
        appendix["excerpt"],
        *(s["text"] for s in appendix["cited_spans"]),
    ]:
        assert domestic not in value and international not in value
        assert not list(phonenumbers.PhoneNumberMatcher(value, "IN"))
    assert ", then " in appendix["excerpt"] and ", and " in appendix["excerpt"]
    assert text(appendix["excerpt"]) == appendix["excerpt"]


def test_hashes_and_identifiers_remain_byte_for_byte_unchanged():
    numeric_identifier = str(synthetic_indian_phone().national_number)
    original = {
        "id": numeric_identifier,
        "case_id": numeric_identifier,
        "report_id": numeric_identifier,
        "evidence_ids": [numeric_identifier],
        "code": "E-0001",
        "case_code": "SYNTHETIC-CASE-0001",
        "sha256": "a" * 24 + numeric_identifier + "b" * 30,
        "url_hash": numeric_identifier,
        "config_digest": numeric_identifier,
        "storage_key": f"SYNTHETIC/{numeric_identifier}",
        "nested": [{"target_id": numeric_identifier, "evidence_codes": ["E-0001"]}],
    }
    assert redact(original) == original
