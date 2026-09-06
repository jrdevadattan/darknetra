"""SYNTHETIC persisted execution graph contract."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4


def event(seq, node_id, parent_id, status, phase):
    return SimpleNamespace(
        seq=seq,
        type="activity.updated",
        at=datetime.now(UTC),
        data={
            "id": str(node_id),
            "parent_id": str(parent_id),
            "kind": "tool",
            "label": "SYNTHETIC tool",
            "status": status,
            "phase": phase,
            "summary": "Public status",
        },
    )


def test_projection_distinguishes_repeated_calls_and_retains_phases():
    from darknetra.agent.activity import project

    run_id, first, second = uuid4(), uuid4(), uuid4()
    run = SimpleNamespace(
        id=run_id,
        thread_id=uuid4(),
        case_id=uuid4(),
        status="RUNNING",
        harness="FAKE",
        replayed_from_run_id=None,
    )
    rows = [
        event(1, first, run_id, "running", "fetching"),
        event(2, second, run_id, "running", "fetching"),
        event(3, first, run_id, "completed", "captured"),
    ]
    graph = project(run, rows, cursor=3)
    assert graph.cursor == 3
    assert len(graph.nodes) == 3 and len(graph.edges) == 2
    assert {node.id: node.status for node in graph.nodes}[second] == "running"
    assert len(graph.events) == 3


def test_terminal_run_marks_unfinished_activity_interrupted_without_faking_success():
    from darknetra.agent.activity import project

    run_id, call = uuid4(), uuid4()
    run = SimpleNamespace(
        id=run_id,
        thread_id=uuid4(),
        case_id=uuid4(),
        status="ERROR",
        harness="FAKE",
        replayed_from_run_id=None,
    )
    graph = project(run, [event(1, call, run_id, "running", "fetching")], cursor=2)
    assert graph.nodes[1].status == "interrupted"
    assert graph.nodes[1].terminal_inferred is True
    assert graph.events[0].status == "running"


def test_replay_does_not_invent_reexecuted_tool_nodes():
    from darknetra.agent.activity import project

    run = SimpleNamespace(
        id=uuid4(),
        thread_id=uuid4(),
        case_id=uuid4(),
        status="DONE",
        harness="FAKE",
        replayed_from_run_id=uuid4(),
    )
    graph = project(run, [], cursor=5)
    assert len(graph.nodes) == 1
    assert graph.replayed_from_run_id == run.replayed_from_run_id
