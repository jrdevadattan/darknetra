"""Specialist budgets and provider options cannot widen the root authority."""

import base64
import time
from uuid import uuid4

import pytest
from pydantic import ValidationError

from darknetra.agent.delegation import DelegateTaskInput, ExecutionBudget
from darknetra.agent.harness_claude import build_options
from darknetra.auth.actor import Actor
from darknetra.config import Settings
from darknetra.tools.contracts import AgentRole, ToolContext, ToolError


def test_child_calls_consume_root_limit_and_deadline():
    root = ExecutionBudget(deadline=time.monotonic() + 30, max_tool_calls=2)
    worker = ExecutionBudget(deadline=root.deadline, max_tool_calls=12, parent=root)
    root.consume_tool()
    worker.consume_tool()
    with pytest.raises(ToolError, match="tool call limit"):
        worker.consume_tool()
    assert root.tool_calls == 2 and worker.tool_calls == 1
    worker.deadline = time.monotonic() - 1
    with pytest.raises(ToolError, match="time limit"):
        worker.consume_tool()


def test_worker_options_select_worker_model_and_exclude_delegation():
    material = base64.b64encode(b"s" * 32).decode()
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://synthetic",
        jwt_signing_key_b64=material,
        field_key_b64=material,
        case_lead_model="SYNTHETIC-lead",
        worker_model="SYNTHETIC-worker",
    )
    ctx = ToolContext(
        uuid4(), Actor("SYSTEM", None), None, settings, role=AgentRole.EVIDENCE_ANALYST
    )
    options = build_options(ctx, None, 0.3)
    assert options.model == "SYNTHETIC-worker"
    assert options.max_budget_usd == 0.3
    assert "mcp__darknetra__read_evidence" in options.allowed_tools
    assert "mcp__darknetra__delegate_task" not in options.allowed_tools
    assert "mcp__darknetra__assess_wallet" not in options.allowed_tools
    assert {"Bash", "Agent", "Task", "WebFetch"} <= set(options.disallowed_tools)
    assert options.tools == [] and options.strict_mcp_config


@pytest.mark.parametrize(
    "args",
    [
        {"task": "SYNTHETIC task", "role": "CASE_LEAD"},
        {"task": " ", "role": "REPORTER"},
        {"task": "SYNTHETIC task", "role": "REPORTER", "case_id": "untrusted"},
    ],
)
def test_specialist_request_rejects_role_escalation_and_unbound_inputs(args):
    with pytest.raises(ValidationError):
        DelegateTaskInput.model_validate(args)
