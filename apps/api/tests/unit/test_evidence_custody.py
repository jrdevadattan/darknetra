from __future__ import annotations

from uuid import uuid4

import pytest
from darknetra_api.models.custody import CustodyEvent


def test_custody_events_are_append_only_at_orm_boundary() -> None:
    event = CustodyEvent(
        case_id=uuid4(),
        evidence_id=uuid4(),
        actor_user_id=uuid4(),
        action="PRESERVED",
        request_id=str(uuid4()),
        integrity_sha256="a" * 64,
    )
    event.action = "MUTATED"

    with pytest.raises(RuntimeError, match="append-only"):
        CustodyEvent.assert_not_modified(event)
