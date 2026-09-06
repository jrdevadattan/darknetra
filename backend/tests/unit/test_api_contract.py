"""The required v1 surface from plan11 must not disappear during route assembly."""

import base64
import re

from darknetra.config import Settings
from darknetra.main import create_app

# Case-relative operations. Parameter names are interchangeable, structure is not.
CASE_OPERATIONS = """
GET,PATCH /
POST /close
POST /reopen
POST /archive
GET,POST /members
PATCH,DELETE /members/{id}
GET /timeline
GET /summary
POST /ledger/import
GET,POST /evidence
GET /evidence/{id}
GET /evidence/{id}/original
GET /evidence/{id}/derivatives/{kind}
GET /evidence/{id}/context
POST /evidence/{id}/verify
POST /evidence/{id}/release
POST /evidence/{id}/reprocess
POST /search
GET /entities
GET /entities/{id}
GET /observations/{id}
POST /extraction/run
GET /extraction/runs
POST /analytics/correlate
GET /analytics/links
GET /analytics/links/{id}
GET /analytics/activity
GET /graph
GET /graph/edges/{id}/provenance
POST /wallets/assess
GET /wallets
GET /trends
GET,POST /threads
GET,PATCH /threads/{id}
GET,POST /threads/{id}/messages
GET /threads/{id}/runs/{id}
GET /threads/{id}/runs/{id}/events
POST /threads/{id}/runs/{id}/cancel
POST /threads/{id}/pin
GET,POST /findings
POST /findings/{id}/promote
GET,POST /decisions
GET,POST /watchlists
GET,POST /watchlists/{id}/items
PATCH,DELETE /watchlists/{id}/items/{id}
POST /watchlists/{id}/items/{id}/run
GET /monitor/runs
GET /monitor/hits
GET /alerts
POST /alerts/{id}/ack
POST /alerts/{id}/dismiss
POST /alerts/{id}/escalate
GET /changes
GET,POST /reports
GET /reports/{id}
GET /reports/{id}/download
GET /audit
"""
GLOBAL_OPERATIONS = """
POST /auth/login
POST /auth/refresh
POST /auth/logout
POST /auth/change-password
GET /auth/me
GET,POST /auth/tokens
DELETE /auth/tokens/{id}
GET,POST /cases
GET,POST /admin/taxonomy
PATCH /admin/taxonomy/{id}
GET,PATCH /admin/settings
GET /tools
POST /tools/{name}/health
GET /audit
GET,POST /users
PATCH /users/{id}
GET /health/live
GET /health/ready
"""


def normalize(path):
    return re.sub(r"\{[^}]+\}", "{}", path.rstrip("/"))


def schema():
    key = base64.b64encode(b"SYNTHETIC".ljust(32, b"0")).decode()
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://synthetic@localhost/synthetic_test",
        jwt_signing_key_b64=key,
        field_key_b64=key,
    )
    return create_app(settings).openapi()


def test_all_planned_v1_operations_are_registered():
    document = schema()
    actual = {
        (method.upper(), normalize(path))
        for path, operations in document["paths"].items()
        for method in operations
    }
    missing = []
    for prefix, text in (
        ("/api/v1/cases/{case_id}", CASE_OPERATIONS),
        ("/api/v1", GLOBAL_OPERATIONS),
    ):
        for line in text.strip().splitlines():
            methods, path = line.split()
            for method in methods.split(","):
                operation = (method, normalize(prefix + path))
                if operation not in actual:
                    missing.append(operation)
    assert not missing, missing


def test_openapi_validation_errors_use_actual_error_envelope():
    document = schema()
    response = document["paths"]["/api/v1/cases"]["post"]["responses"]["422"]
    assert response["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorEnvelope")
    assert not any(
        "password" in field.lower()
        for field in document["components"]["schemas"]["User"]["properties"]
        if field != "must_change_password"
    )
