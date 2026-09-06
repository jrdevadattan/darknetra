"""Typed contracts shared by every model adapter and monitoring caller."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from darknetra.auth.actor import Actor
from darknetra.config import Settings


class Lane(StrEnum):
    EVIDENCE = "EVIDENCE"
    ANALYTICS = "ANALYTICS"
    CASE = "CASE"
    SURFACE = "SURFACE"
    DARK = "DARK"
    CHAIN = "CHAIN"
    IDENTITY = "IDENTITY"
    TELEGRAM = "TELEGRAM"


class AgentRole(StrEnum):
    CASE_LEAD = "CASE_LEAD"
    EVIDENCE_ANALYST = "EVIDENCE_ANALYST"
    SURFACE_SCOUT = "SURFACE_SCOUT"
    DARK_SCOUT = "DARK_SCOUT"
    CHAIN_ANALYST = "CHAIN_ANALYST"
    IDENTITY_SCOUT = "IDENTITY_SCOUT"
    REPORTER = "REPORTER"


class ToolError(Exception):
    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.detail = code, message, detail or {}


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    evidence_ids: list[UUID] = Field(default_factory=list)
    truncated: bool = False


async def no_emit(event: dict[str, Any]) -> None:
    pass


@dataclass
class ToolContext:
    case_id: UUID
    actor: Actor
    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings
    thread_id: UUID | None = None
    run_id: UUID | None = None
    watchlist_item_id: UUID | None = None
    role: AgentRole = AgentRole.CASE_LEAD
    emit: Callable[[dict[str, Any]], Awaitable[None]] = no_emit
    cache: dict[str, ToolResult] = field(default_factory=dict)
    context_evidence_codes: list[str] = field(default_factory=list)
    agent_id: UUID | None = None
    parent_call_id: UUID | None = None
    transport: str = "internal"
    delegation: Any = None
    execution_budget: Any = None
    disabled_tools: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    lane: Lane
    impl: Callable[[ToolContext, BaseModel], Awaitable[BaseModel]]
    allowed_for: frozenset[AgentRole]
    requires_network: bool = False
    source_class: str | None = None
    policy_tags: frozenset[str] = frozenset()
    rate_key: str | None = None
    capture: bool = False
    timeout_s: float = 60.0
    max_result_chars: int = 40000
    unavailable_reason: str | None = None
