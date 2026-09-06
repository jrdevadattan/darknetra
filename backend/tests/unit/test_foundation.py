import base64
import importlib.util

import pytest
from pydantic import ValidationError


def test_foundation_modules_exist():
    assert importlib.util.find_spec("darknetra.config") is not None


def test_keys_are_required_validated_and_hidden(monkeypatch):
    from darknetra.config import Settings

    monkeypatch.delenv("DARKNETRA_JWT_SIGNING_KEY_B64", raising=False)
    monkeypatch.delenv("DARKNETRA_FIELD_KEY_B64", raising=False)
    key = base64.b64encode(b"x" * 32).decode()
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql+psycopg://x")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://x",
            jwt_signing_key_b64="bad",
            field_key_b64=key,
        )
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://x",
        jwt_signing_key_b64=key,
        field_key_b64=key,
    )
    assert settings.jwt_signing_key == b"x" * 32
    assert key not in repr(settings)


def test_span_and_public_harness_validation():
    from darknetra.api.v1.schemas.common import Span
    from darknetra.api.v1.schemas.threads import ThreadCreate

    with pytest.raises(ValidationError):
        Span(start=4, end=4)
    with pytest.raises(ValidationError):
        ThreadCreate(title="test", harness="FAKE")


def test_case_isolation_constraints_and_complete_metadata():
    import darknetra.models  # noqa: F401
    from darknetra.db import Base

    required = {
        "evidence",
        "observations",
        "chunks",
        "ledger_nodes",
        "ledger_edges",
        "reports",
        "decisions",
        "run_events",
        "tool_registry",
    }
    assert required <= set(Base.metadata.tables)
    for table in ("observations", "chunks", "ledger_edges", "reports"):
        assert any(
            len(fk.column_keys) > 1 for fk in Base.metadata.tables[table].foreign_key_constraints
        )


def test_validation_response_does_not_echo_password():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel

    from darknetra.errors import register_error_handlers

    class Body(BaseModel):
        password: int

    app = FastAPI()
    register_error_handlers(app)

    @app.post("/")
    def endpoint(body: Body):
        return {}

    response = TestClient(app).post("/", json={"password": "secret-must-never-echo"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION"
    assert "secret-must-never-echo" not in response.text


@pytest.mark.parametrize(
    "values",
    [
        {"max_requests_per_hour": {"unknown": 1}},
        {"max_requests_per_hour": {"surface": -1}},
        {"retention_days": -1},
    ],
)
def test_policy_rejects_invalid_caps(values):
    from darknetra.api.v1.schemas.cases import SourcePolicy

    with pytest.raises(ValidationError):
        SourcePolicy(**values)


@pytest.mark.parametrize(
    "values",
    [
        {"scopes": []},
        {"scopes": ["unknown:scope"]},
        {"scopes": ["alerts:read"], "expires_in_days": 0},
        {"scopes": ["alerts:read"], "expires_in_days": 366},
    ],
)
def test_token_scope_and_expiry_limits(values):
    from darknetra.api.v1.schemas.auth import TokenCreate

    with pytest.raises(ValidationError):
        TokenCreate(name="Service", **values)


def test_password_and_title_limits():
    from darknetra.api.v1.schemas.auth import ChangePasswordRequest
    from darknetra.api.v1.schemas.cases import CaseCreate
    from darknetra.api.v1.schemas.threads import ThreadPatch

    with pytest.raises(ValidationError):
        ChangePasswordRequest(current_password="old", new_password="short")
    with pytest.raises(ValidationError):
        CaseCreate(title="x" * 301)
    with pytest.raises(ValidationError):
        ThreadPatch(harness="FAKE")


def test_invalid_secret_is_hidden_in_printable_settings_error():
    from darknetra.config import Settings

    sentinel = "malformed-secret-never-print-this"
    with pytest.raises(ValidationError) as caught:
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://x",
            jwt_signing_key_b64=sentinel,
            field_key_b64=sentinel,
        )
    assert sentinel not in str(caught.value)
    assert sentinel not in repr(caught.value)


def test_database_constraint_names_are_unique():
    from sqlalchemy.dialects.postgresql import dialect
    from sqlalchemy.schema import CreateTable

    import darknetra.models  # noqa: F401
    from darknetra.db import Base

    for table in Base.metadata.tables.values():
        names = [c.name for c in table.constraints if c.name]
        assert len(names) == len(set(names)), table.name
        assert str(CreateTable(table).compile(dialect=dialect()))


def test_request_ids_accept_opaque_text():
    from sqlalchemy import Text

    from darknetra.audit.models import AuditEvent
    from darknetra.decisions.models import Decision
    from darknetra.evidence.models import CustodyEvent

    for model in (AuditEvent, CustodyEvent, Decision):
        assert isinstance(model.__table__.c.request_id.type, Text)


def test_decision_supersession_preserves_target_identity():
    from sqlalchemy import CheckConstraint

    from darknetra.decisions.models import Decision

    table = Decision.__table__
    supersession = next(
        fk for fk in table.foreign_key_constraints if "supersedes_id" in fk.column_keys
    )
    assert supersession.column_keys == [
        "case_id",
        "target_type",
        "target_id",
        "target_version",
        "supersedes_id",
    ]
    assert [element.target_fullname for element in supersession.elements] == [
        "decisions.case_id",
        "decisions.target_type",
        "decisions.target_id",
        "decisions.target_version",
        "decisions.id",
    ]
    assert any(
        isinstance(c, CheckConstraint)
        and str(c.sqltext) == "supersedes_id IS NULL OR supersedes_id <> id"
        for c in table.constraints
    )
