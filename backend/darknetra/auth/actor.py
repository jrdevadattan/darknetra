from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class Actor:
    kind: Literal["USER", "TOKEN", "SYSTEM", "MODEL"]
    id: UUID | None
    global_role: str | None = None
    scopes: frozenset[str] = frozenset()
    session_id: UUID | None = None
    user_id: UUID | None = None
    token_case_id: UUID | None = None
    display: str = "System"
    must_change_password: bool = False
