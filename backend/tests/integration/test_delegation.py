"""Scenario 18/19/23: real specialist execution keeps claims, authority and cost bounded."""

import asyncio
import json
import time
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from darknetra.agent.models import Message, Run, RunEvent, Thread
from darknetra.tools.contracts import AgentRole
from darknetra.tools.invoke import invoke


async def setup_run(client, app, actor_login, harness):
    await actor_login()
    case = (await client.post("/api/v1/cases", json={"title": "SYNTHETIC delegation"})).json()
    prefix = f"/api/v1/cases/{case['id']}"
    upload = await client.post(
        prefix + "/evidence",
        files={"files": ("SYNTHETIC.txt", b"SYNTHETIC blue parcel")},
        data={"source_class": "SYNTHETIC"},
    )
    evidence = upload.json()["results"][0]["evidence"]
    await app.state.jobs.wait_all()
    thread = (await client.post(prefix + "/threads", json={"title": "SYNTHETIC worker"})).json()
    app.state.harness_factory = lambda _: harness
    response = await client.post(
        prefix + f"/threads/{thread['id']}/messages",
        json={"content": "Review attachment with a specialist", "attachments": [evidence["code"]]},
    )
    assert response.status_code == 202, response.text
    return case, thread, response.json()["run_id"], evidence


async def test_specialist_is_invoked_and_claim_checked_without_main_message(
    client, app, actor_login
):
    results = {}

    class Harness:
        async def run(self, ctx, prompt, **kwargs):
            if ctx.role == AgentRole.CASE_LEAD:
                results["parent_budget"] = kwargs["budget"]
                results["delegate"] = await invoke(
                    ctx,
                    "delegate_task",
                    {
                        "task": "Read the attached SYNTHETIC evidence",
                        "role": "EVIDENCE_ANALYST",
                    },
                )
                yield {"type": "assistant", "text": "Insufficient evidence."}
                yield {"type": "usage", "cost_usd": "0.1", "tokens_in": 3, "tokens_out": 4}
            else:
                results["worker_budget"] = kwargs["budget"]
                results["worker"] = ctx
                results["read"] = await invoke(
                    ctx,
                    "read_evidence",
                    {
                        "evidence_code": ctx.context_evidence_codes[0],
                        "max_chars": 1200,
                    },
                )
                results["recursive"] = await invoke(
                    ctx,
                    "delegate_task",
                    {
                        "task": "SYNTHETIC recursive attempt",
                        "role": "REPORTER",
                    },
                )
                results["forbidden"] = await invoke(ctx, "assess_wallet", {})
                code = ctx.context_evidence_codes[0]
                text = f"SYNTHETIC blue parcel [{code}]"
                claims = [{"text": text, "evidence_codes": [code], "kind": "observed"}]
                yield {
                    "type": "assistant",
                    "text": text + "\n```claims\n" + json.dumps(claims) + "\n```",
                }
                yield {"type": "usage", "cost_usd": "0.2", "tokens_in": 10, "tokens_out": 20}

    case, thread, run_id, evidence = await setup_run(client, app, actor_login, Harness())
    await app.state.jobs.wait_all()
    assert results["delegate"].ok, results["delegate"].error
    assert results["read"].ok
    assert results["recursive"].error["code"] == "POLICY_DENIED"
    assert results["forbidden"].error["code"] == "POLICY_DENIED"
    assert results["worker"].case_id == UUID(case["id"])
    assert results["worker"].agent_id != results["worker"].run_id
    assert results["parent_budget"] + results["worker_budget"] <= 2
    data = results["delegate"].data
    assert data["verification"]["ok"] and data["claims"][0]["verified"]
    assert UUID(evidence["id"]) in results["delegate"].evidence_ids
    async with app.state.session_factory() as db:
        run = await db.get(Run, UUID(run_id))
        saved_thread = await db.get(Thread, UUID(thread["id"]))
        assert run.cost_usd == saved_thread.spent_usd == Decimal("0.3")
        assert (run.tokens_in, run.tokens_out) == (13, 24)
        messages = list(
            (
                await db.scalars(
                    select(Message).where(
                        Message.case_id == UUID(case["id"]),
                        Message.run_id == UUID(run_id),
                        Message.role == "ASSISTANT",
                    )
                )
            ).all()
        )
        assert len(messages) == 1 and messages[0].text == "Insufficient evidence."
        events = list(
            (
                await db.scalars(
                    select(RunEvent)
                    .where(
                        RunEvent.case_id == UUID(case["id"]),
                        RunEvent.run_id == UUID(run_id),
                        RunEvent.type == "activity.updated",
                    )
                    .order_by(RunEvent.seq)
                )
            ).all()
        )
        agent_events = [
            event.data
            for event in events
            if event.data.get("kind") == "agent" and event.data["id"] != run_id
        ]
        assert [event["status"] for event in agent_events] == ["running", "completed"]


@pytest.mark.parametrize("usage_first", [True, False])
async def test_unverified_worker_output_is_withheld_and_usage_charged(
    client, app, actor_login, usage_first
):
    results = []

    class Harness:
        async def run(self, ctx, prompt, **kwargs):
            if ctx.role == AgentRole.CASE_LEAD:
                results.append(
                    await invoke(
                        ctx, "delegate_task", {"task": "SYNTHETIC review", "role": "REPORTER"}
                    )
                )
                yield {"type": "assistant", "text": "Insufficient evidence."}
            else:
                if usage_first:
                    yield {"type": "usage", "cost_usd": "0.2"}
                yield {"type": "assistant", "text": "Uncited invented identity."}
                if not usage_first:
                    yield {"type": "usage", "cost_usd": "0.2"}

    _, _, run_id, _ = await setup_run(client, app, actor_login, Harness())
    await app.state.jobs.wait_all()
    assert not results[0].ok and results[0].error["code"] == "VALIDATION"
    assert "Uncited invented identity" not in results[0].model_dump_json()
    async with app.state.session_factory() as db:
        assert (await db.get(Run, UUID(run_id))).cost_usd == Decimal("0.2")


@pytest.mark.parametrize("behavior", ["limit", "failure", "cancel"])
async def test_worker_limits_failures_and_cancel_keep_usage(client, app, actor_login, behavior):
    results = []

    class Harness:
        async def run(self, ctx, prompt, **kwargs):
            if ctx.role == AgentRole.CASE_LEAD:
                for index in range(4 if behavior == "limit" else 1):
                    results.append(
                        await invoke(
                            ctx,
                            "delegate_task",
                            {
                                "task": f"SYNTHETIC review {index}",
                                "role": "REPORTER",
                            },
                        )
                    )
                yield {"type": "assistant", "text": "Insufficient evidence."}
            else:
                yield {"type": "usage", "cost_usd": "0.1", "tokens_in": 2, "tokens_out": 1}
                if behavior == "cancel":
                    raise asyncio.CancelledError
                if behavior == "failure":
                    raise RuntimeError("SYNTHETIC worker failure")
                yield {"type": "assistant", "text": "Insufficient evidence."}

    _, _, run_id, _ = await setup_run(client, app, actor_login, Harness())
    await app.state.jobs.wait_all()
    async with app.state.session_factory() as db:
        run = await db.get(Run, UUID(run_id))
        assert run.cost_usd == (Decimal("0.3") if behavior == "limit" else Decimal("0.1"))
        if behavior == "cancel":
            assert run.status == "CANCELLED"
        elif behavior == "failure":
            assert not results[0].ok
        else:
            assert len(results) == 4 and sum(result.ok for result in results) == 3
            assert results[-1].error["code"] == "BUDGET_EXCEEDED"


async def test_failed_workers_do_not_reallocate_unreported_provider_budget(
    client, app, actor_login
):
    allocations = []

    class Harness:
        async def run(self, ctx, prompt, **kwargs):
            allocations.append(kwargs["budget"])
            if ctx.role == AgentRole.CASE_LEAD:
                # The provider is stubbed, but preserve Claude's missing-usage semantics.
                ctx.delegation.mode = "CLAUDE"
                for index in range(3):
                    await invoke(
                        ctx,
                        "delegate_task",
                        {
                            "task": f"SYNTHETIC unavailable provider {index}",
                            "role": "REPORTER",
                        },
                    )
                yield {"type": "assistant", "text": "Insufficient evidence."}
            else:
                raise RuntimeError("SYNTHETIC provider disconnected before usage")

    _, _, run_id, _ = await setup_run(client, app, actor_login, Harness())
    await app.state.jobs.wait_all()
    assert len(allocations) == 4
    assert sum(allocations) <= 2
    async with app.state.session_factory() as db:
        finished = await db.scalar(
            select(RunEvent).where(
                RunEvent.run_id == UUID(run_id),
                RunEvent.type == "run.finished",
            )
        )
        assert finished.data["cost_complete"] is False


async def test_root_deadline_is_a_budget_stop(client, app, actor_login, monkeypatch):
    from darknetra.agent.delegation import ExecutionBudget

    monkeypatch.setattr(
        "darknetra.agent.service.ExecutionBudget",
        lambda **kwargs: ExecutionBudget(deadline=time.monotonic() + 0.1),
    )

    class Harness:
        async def run(self, ctx, prompt, **kwargs):
            await asyncio.Event().wait()
            yield {"type": "assistant", "text": "Insufficient evidence."}

    _, _, run_id, _ = await setup_run(client, app, actor_login, Harness())
    await app.state.jobs.wait_all()
    async with app.state.session_factory() as db:
        run = await db.get(Run, UUID(run_id))
        assert run.status == "BUDGET"
        assert run.error["code"] == "BUDGET_EXCEEDED"


async def test_cancelling_root_stops_awaited_worker_and_charges_usage(client, app, actor_login):
    ready, stopped = asyncio.Event(), asyncio.Event()

    class Harness:
        async def run(self, ctx, prompt, **kwargs):
            if ctx.role == AgentRole.CASE_LEAD:
                await invoke(
                    ctx, "delegate_task", {"task": "SYNTHETIC slow work", "role": "REPORTER"}
                )
                yield {"type": "assistant", "text": "Insufficient evidence."}
            else:
                try:
                    yield {"type": "usage", "cost_usd": "0.1"}
                    ready.set()
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

    case, thread, run_id, _ = await setup_run(client, app, actor_login, Harness())
    await asyncio.wait_for(ready.wait(), 10)
    response = await client.post(
        f"/api/v1/cases/{case['id']}/threads/{thread['id']}/runs/{run_id}/cancel"
    )
    assert response.status_code == 202, response.text
    await app.state.jobs.wait_all()
    assert stopped.is_set()
    async with app.state.session_factory() as db:
        run = await db.get(Run, UUID(run_id))
        assert run.status == "CANCELLED" and run.cost_usd == Decimal("0.1")


async def test_worker_budget_error_closes_provider_stream(client, app, actor_login):
    closed = asyncio.Event()
    streams, checked = [], []

    class Harness:
        def run(self, ctx, prompt, **kwargs):
            stream = self.iterate(ctx)
            streams.append(stream)
            return stream

        async def iterate(self, ctx):
            if ctx.role == AgentRole.CASE_LEAD:
                result = await invoke(
                    ctx,
                    "delegate_task",
                    {
                        "task": "SYNTHETIC budget stop",
                        "role": "REPORTER",
                    },
                )
                checked.append((result, closed.is_set()))
                yield {"type": "assistant", "text": "Insufficient evidence."}
            else:
                try:
                    yield {"type": "usage", "cost_usd": "1.1"}
                    await asyncio.Event().wait()
                finally:
                    closed.set()

    await setup_run(client, app, actor_login, Harness())
    await app.state.jobs.wait_all()
    assert checked[0][0].error["code"] == "BUDGET_EXCEEDED"
    assert checked[0][1], "The provider stream must close before the lead resumes"
