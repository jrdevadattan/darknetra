"""One-level, sequential specialist workers with a reserved share of the root budget.

Concurrency is deliberately one. Workers share authority and total tool/deadline limits,
but never conversation output or tool caches. Only verified output returns to the lead.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from darknetra.agent.claim_checker import extract_claims, verify
from darknetra.agent.harness_base import Harness, managed_events
from darknetra.api.v1.schemas.threads import Claim, Verification
from darknetra.evidence.models import Evidence
from darknetra.tools.contracts import AgentRole, ToolContext, ToolError

SpecialistRole = Literal[
    "EVIDENCE_ANALYST", "SURFACE_SCOUT", "DARK_SCOUT", "CHAIN_ANALYST", "IDENTITY_SCOUT", "REPORTER"
]


class DelegateTaskInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    task: str = Field(min_length=1, max_length=4000)
    role: SpecialistRole


class EvidenceReference(BaseModel):
    id: UUID
    code: str


class DelegateTaskOutput(BaseModel):
    agent_id: UUID
    role: AgentRole
    text: str
    claims: list[Claim]
    verification: Verification
    evidence: list[EvidenceReference]
    cost_usd: float


@dataclass
class ExecutionBudget:
    deadline: float
    max_tool_calls: int = 48
    tool_calls: int = 0
    parent: "ExecutionBudget | None" = None

    def remaining_seconds(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ToolError("BUDGET_EXCEEDED", "Agent time limit reached")
        return remaining

    def consume_tool(self) -> None:
        self.remaining_seconds()
        if self.tool_calls >= self.max_tool_calls:
            raise ToolError("BUDGET_EXCEEDED", "Agent tool call limit reached")
        if self.parent is not None:
            self.parent.consume_tool()
        self.tool_calls += 1


@dataclass
class DelegationState:
    mode: str
    harness_factory: Callable[[str], Harness]
    parent_budget: Decimal
    worker_pool: Decimal
    execution_budget: ExecutionBudget
    children: int = 0
    spent: Decimal = Decimal("0")
    tokens_in: int = 0
    tokens_out: int = 0
    cost_complete: bool = True
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


async def run_specialist(ctx: ToolContext, request: DelegateTaskInput) -> DelegateTaskOutput:
    state = ctx.delegation
    if ctx.role != AgentRole.CASE_LEAD or not isinstance(state, DelegationState):
        raise ToolError("POLICY_DENIED", "Delegation is available only to an active case lead")
    if not ctx.run_id or not ctx.thread_id:
        raise ToolError("POLICY_DENIED", "Delegation requires an active case run")
    async with state.lock:
        state.execution_budget.remaining_seconds()
        if state.children >= 3 or state.spent >= state.worker_pool:
            raise ToolError("BUDGET_EXCEEDED", "Specialist allocation exhausted")
        # The lead cannot spend this pool: its provider cap is a separate fixed half.
        # Never reallocate unused or unreported charges: each child owns one fixed
        # third, even if an earlier provider disconnected before returning usage.
        allocation = state.worker_pool / 3
        if state.spent + allocation > state.worker_pool:
            raise ToolError("BUDGET_EXCEEDED", "Specialist allocation exhausted")
        state.children += 1
        child_id = uuid4()
        role = AgentRole(request.role)
        label = role.value.replace("_", " ").capitalize()
        parent_id = ctx.parent_call_id or ctx.agent_id or ctx.run_id

        async def activity(status: str) -> None:
            await ctx.emit(
                {
                    "type": "activity.updated",
                    "data": {
                        "id": str(child_id),
                        "parent_id": str(parent_id),
                        "kind": "agent",
                        "label": label,
                        "agent_role": role.value,
                        "status": status,
                        "phase": {
                            "running": "working",
                            "completed": "complete",
                            "cancelled": "cancelled",
                            "failed": "error",
                            "denied": "error",
                        }[status],
                        "summary": {
                            "running": "Specialist reviewing case evidence",
                            "completed": "Specialist result verified",
                            "cancelled": "Specialist cancelled",
                            "failed": "Specialist could not complete",
                            "denied": "Specialist unavailable or denied",
                        }[status],
                    },
                }
            )

        child = replace(
            ctx,
            role=role,
            cache={},
            context_evidence_codes=list(ctx.context_evidence_codes),
            agent_id=child_id,
            parent_call_id=None,
            delegation=None,
            execution_budget=ExecutionBudget(
                deadline=min(state.execution_budget.deadline, time.monotonic() + 90),
                max_tool_calls=12,
                parent=state.execution_budget,
            ),
        )
        cost = Decimal("0")
        usage_received = state.mode != "CLAUDE"
        verified_text = ""
        verified_claims: list[Claim] = []
        buffered_text = ""
        output_chars = 0
        claims_failed = False

        async def check_text(text: str) -> None:
            nonlocal verified_text, verified_claims, output_chars, claims_failed
            output_chars += len(text)
            if output_chars > 16000:
                raise ToolError("VALIDATION", "Specialist output exceeds the bounded result size")
            prose, claims = extract_claims(text)
            async with ctx.session_factory() as session:
                verification = await verify(session, ctx.case_id, claims)
            if not verification.ok:
                # Drain the bounded provider response to receive its final usage even
                # when prose is rejected; no rejected text is returned or emitted.
                claims_failed = True
                return
            verified_text, verified_claims = prose, claims

        await activity("running")
        try:
            async with (
                asyncio.timeout(child.execution_budget.remaining_seconds()),
                managed_events(
                    state.harness_factory(state.mode).run(
                        child,
                        request.task,
                        goal="Complete only the assigned specialist task.",
                        history=None,
                        budget=float(allocation),
                    )
                ) as events,
            ):
                async for event in events:
                    kind = event.get("type")
                    if kind == "usage":
                        usage_received = True
                        amount = Decimal(str(event.get("cost_usd", 0)))
                        if not amount.is_finite() or amount < 0:
                            raise ToolError("UNAVAILABLE", "Invalid provider usage")
                        cost += amount
                        state.spent += amount
                        state.tokens_in += max(0, int(event.get("tokens_in", 0)))
                        state.tokens_out += max(0, int(event.get("tokens_out", 0)))
                        if cost > allocation:
                            raise ToolError("BUDGET_EXCEEDED", "Specialist budget exhausted")
                    elif kind == "assistant":
                        await check_text(event.get("text", ""))
                        buffered_text = ""
                    elif kind == "message.delta":
                        buffered_text += event.get("data", {}).get("text", "")
                        if len(buffered_text) > 16000:
                            raise ToolError(
                                "VALIDATION", "Specialist output exceeds the bounded result size"
                            )
                    # Provider events, prose and reasoning never reach the activity stream.
                if buffered_text:
                    await check_text(buffered_text)
            if claims_failed:
                raise ToolError("VALIDATION", "Specialist result failed citation verification")
            if not verified_text:
                raise ToolError("UNAVAILABLE", "Specialist returned no verified result")
            codes = {code for claim in verified_claims for code in claim.evidence_codes}
            async with ctx.session_factory() as session:
                rows = (
                    list(
                        (
                            await session.scalars(
                                select(Evidence).where(
                                    Evidence.case_id == ctx.case_id,
                                    Evidence.code.in_(codes),
                                )
                            )
                        ).all()
                    )
                    if codes
                    else []
                )
            output = DelegateTaskOutput(
                agent_id=child_id,
                role=role,
                text=verified_text,
                claims=verified_claims,
                verification=Verification(ok=True, unverified_count=0, revised=False),
                evidence=[EvidenceReference(id=row.id, code=row.code) for row in rows],
                cost_usd=float(cost),
            )
        except asyncio.CancelledError:
            await activity("cancelled")
            raise
        except TimeoutError:
            await activity("failed")
            raise ToolError("BUDGET_EXCEEDED", "Specialist time limit reached") from None
        except Exception:
            await activity("failed")
            raise
        finally:
            state.cost_complete &= usage_received
        await activity("completed")
        return output
