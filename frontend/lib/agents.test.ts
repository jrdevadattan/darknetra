import { expect, test } from "vitest";
import { applyCliEvent } from "./codex";
import { agentIdentity, applyAgentRecords, settleAgents } from "./agents";
import type { ChatMessage } from "./chat-types";

test("specialists appear only after a recorded id and keep separate statuses and results", () => {
  const message: ChatMessage = {
    id: "SYNTHETIC",
    role: "assistant",
    text: "",
    at: "",
    status: "running",
    activity: [],
  };
  applyCliEvent(message, {
    type: "item.started",
    item: {
      id: "spawn",
      type: "collab_tool_call",
      tool: "spawn_agent",
      prompt: "SYNTHETIC review",
    },
  });
  expect(message.agents || []).toHaveLength(0);
  applyCliEvent(message, {
    type: "item.completed",
    item: {
      id: "spawn",
      type: "collab_tool_call",
      tool: "spawn_agent",
      prompt: "SYNTHETIC review",
      receiver_thread_ids: ["first"],
      agents_states: { first: { status: "running" } },
    },
  });
  applyCliEvent(message, {
    type: "item.completed",
    item: {
      id: "wait",
      type: "collab_tool_call",
      tool: "wait",
      agents_states: {
        first: { status: "completed", message: "SYNTHETIC finding" },
        second: { status: "errored", message: "SYNTHETIC unavailable" },
      },
    },
  });
  expect(message.agents).toMatchObject([
    {
      id: "first",
      task: "SYNTHETIC review",
      status: "completed",
      result: "SYNTHETIC finding",
    },
    { id: "second", status: "error" },
  ]);
  applyCliEvent(message, {
    type: "item.completed",
    item: {
      id: "close",
      type: "collab_tool_call",
      tool: "close_agent",
      agents_states: { first: { status: "shutdown" } },
    },
  });
  expect(message.agents?.[0].status).toBe("completed");
});

test("nickname metadata is accepted only for the exact child and parent", () => {
  const meta = {
    type: "session_meta",
    payload: {
      id: "SYNTHETIC-child",
      parent_thread_id: "SYNTHETIC-parent",
      agent_nickname: "Records Analyst",
      agent_role: "records_analyst",
    },
  };
  expect(agentIdentity(meta, "SYNTHETIC-child", "SYNTHETIC-parent")).toEqual({
    name: "Records Analyst",
    role: "records_analyst",
  });
  expect(
    agentIdentity(meta, "SYNTHETIC-child", "another-case"),
  ).toBeUndefined();
});

test("v2 child records expose real completion, ignore inherited history and never copy reasoning", () => {
  const message: ChatMessage = {
    id: "SYNTHETIC",
    role: "assistant",
    text: "",
    at: "2026-09-08T08:00:00Z",
    status: "running",
    activity: [],
  };
  applyAgentRecords(
    message,
    "SYNTHETIC-child",
    { timestamp: "2026-09-08T08:00:20Z", agent_path: "/root/reference_check" },
    [
      {
        type: "event_msg",
        payload: {
          type: "task_started",
          turn_id: "parent",
          started_at: Date.parse(message.at) / 1000,
        },
      },
      {
        type: "event_msg",
        payload: {
          type: "task_complete",
          turn_id: "parent",
          last_agent_message: "SYNTHETIC parent result must not appear",
        },
      },
      {
        type: "event_msg",
        payload: {
          type: "task_started",
          turn_id: "child",
          started_at: Date.parse("2026-09-08T08:00:20Z") / 1000,
        },
      },
      {
        type: "response_item",
        payload: { type: "reasoning", text: "SYNTHETIC private reasoning" },
      },
      {
        type: "event_msg",
        payload: {
          type: "task_complete",
          turn_id: "child",
          last_agent_message: "SYNTHETIC child result",
        },
      },
    ],
  );
  expect(message.agents).toMatchObject([
    {
      task: "Assignment: reference check",
      status: "completed",
      result: "SYNTHETIC child result",
    },
  ]);
  expect(JSON.stringify(message)).not.toContain("parent result");
  expect(JSON.stringify(message)).not.toContain("private reasoning");
  message.agents!.push({
    id: "pending",
    name: "Case Specialist",
    task: "",
    status: "running",
  });
  message.status = "error";
  settleAgents(message);
  expect(message.agents![1].status).toBe("unverified");
});
