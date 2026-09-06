"""Response media types and bounded derivatives must match actual HTTP transport."""

from test_api_contract import schema


def test_stream_original_and_derivative_response_contracts():
    paths = schema()["paths"]
    events = paths["/api/v1/cases/{case_id}/threads/{thread_id}/runs/{run_id}/events"]["get"][
        "responses"
    ]["200"]["content"]
    assert set(events) == {"text/event-stream"}
    original = paths["/api/v1/cases/{case_id}/evidence/{eid}/original"]["get"]["responses"]["200"][
        "content"
    ]
    assert set(original) == {"application/octet-stream"}
    derivative = paths["/api/v1/cases/{case_id}/evidence/{eid}/derivatives/{kind}"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert len(derivative["anyOf"]) == 5
