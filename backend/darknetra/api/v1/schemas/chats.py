from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["AUTO", "CLAUDE", "NIM", "OFFLINE", "DETERMINISTIC"]


class ChatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    provider: Provider = "AUTO"
    budget_usd: Decimal = Field(default=Decimal("2"), gt=0, le=100)


class ChatPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=200)
    status: Literal["OPEN", "CLOSED"] | None = None
    provider: Provider | None = None
    budget_usd: Decimal | None = Field(None, gt=0, le=100)


class Chat(ChatCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    spent_usd: Decimal
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=16000)


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    thread_id: UUID
    run_id: UUID | None
    role: str
    text: str
    blocks: list[Any]
    provider: str | None
    at: datetime
    verification: dict[str, str] = Field(
        default_factory=lambda: {
            "mode": "NOT_APPLICABLE",
            "reason": "private_chat_has_no_case_evidence",
        }
    )


class Run(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    thread_id: UUID
    status: str
    provider: str
    started_at: datetime | None
    finished_at: datetime | None
    cost_usd: Decimal
    cost_complete: bool
    tokens_in: int
    tokens_out: int
    error: dict[str, Any] | None


class RunRef(BaseModel):
    run_id: UUID
    chat_id: UUID
    status: str
