import { expect, test, vi } from "vitest";
import { cliArgs, applyCliEvent } from "./codex";
import { assertLocalRequest } from "./local-request";
import type { ChatMessage } from "./chat-types";

test("a configured bot never gains shell write access or exposes credentials in arguments", () => {
  try {
    vi.stubEnv("TELEGRAM_BOT_TOKEN", "");
    vi.stubEnv("TELEGRAM_CHAT_ID", "");
    expect(
      cliArgs(undefined, "normal").filter((arg) =>
        arg.startsWith("sandbox_workspace_write.writable_roots="),
      ),
    ).toEqual([]);
    vi.stubEnv("TELEGRAM_BOT_TOKEN", "123456:SYNTHETIC_token");
    vi.stubEnv("TELEGRAM_CHAT_ID", "-100123");
    const args = cliArgs(undefined, "normal");
    expect(
      args.filter((arg) =>
        arg.startsWith("sandbox_workspace_write.writable_roots="),
      ),
    ).toEqual([]);
    expect(args).toContain('permissions.research.extends=":read-only"');
    expect(args.join(" ")).not.toContain("SYNTHETIC_token");
  } finally {
    vi.unstubAllEnvs();
  }
});

test("resumes only the selected CLI session and passes prompts over stdin", () => {
  const args = cliArgs("synthetic-session", "normal");
  expect(args.slice(-3)).toEqual(["resume", "synthetic-session", "-"]);
  expect(args).toContain("--ignore-user-config");
  expect(args).not.toContain("--last");
  expect(args).not.toContain("--dangerously-bypass-approvals-and-sandbox");
  expect(args).toContain('permissions.research.extends=":read-only"');
  expect(args).toContain("permissions.research.network.enabled=true");
  expect(args).toContain("features.apps=false");
  expect(args.some((arg) => arg.startsWith("mcp_servers."))).toBe(false);
  expect(args).not.toContain("call-actor");
  expect(args).toContain(
    'agents.research_analyst.nickname_candidates=["Research Analyst"]',
  );
  expect(args).toContain(
    'agents.records_analyst.nickname_candidates=["Records Analyst"]',
  );
  expect(args).toContain(
    'agents.file_examiner.nickname_candidates=["File Examiner"]',
  );
  for (const [role, name] of [
    ["financial_analyst", "Financial Analyst"],
    ["log_review_analyst", "Log Review Analyst"],
    ["logistics_liaison", "Postal Records Liaison"],
    ["case_liaison", "Case Liaison"],
    ["legal_liaison", "Legal Liaison"],
  ])
    expect(args).toContain(
      `agents.${role}.nickname_candidates=${JSON.stringify([name])}`,
    );
  expect(args).toContain("agents.max_depth=1");
  expect(args).toContain("agents.max_concurrent_threads_per_session=2");
});

test("successful completion clears a recovered connection error", () => {
  const message: ChatMessage = {
    id: "synthetic",
    role: "assistant",
    text: "",
    status: "running",
    at: "",
    activity: [],
  };
  applyCliEvent(message, {
    type: "error",
    message: "SYNTHETIC retrying connection",
  });
  applyCliEvent(message, {
    type: "item.completed",
    item: { type: "agent_message", text: "SYNTHETIC recovered" },
  });
  applyCliEvent(message, { type: "turn.completed" });
  expect(message.status).toBe("done");
  expect(message.error).toBeUndefined();
});

test("selected image attachments are passed to new and resumed CLI turns", () => {
  const image = "/tmp/SYNTHETIC-chat/sample.png";
  expect(cliArgs(undefined, "normal", [image]).slice(-3)).toEqual([
    "--image",
    image,
    "-",
  ]);
  expect(cliArgs("SYNTHETIC-session", "normal", [image]).slice(-5)).toEqual([
    "resume",
    "SYNTHETIC-session",
    "--image",
    image,
    "-",
  ]);
});

test("turn failure wins over an earlier answer and private reasoning is omitted", () => {
  const message: ChatMessage = {
    id: "synthetic",
    role: "assistant",
    text: "",
    status: "running",
    at: "",
    activity: [],
  };
  applyCliEvent(message, {
    type: "item.completed",
    item: { type: "reasoning", text: "SYNTHETIC private reasoning" },
  });
  applyCliEvent(message, {
    type: "item.completed",
    item: { type: "agent_message", text: "SYNTHETIC partial answer" },
  });
  applyCliEvent(message, {
    type: "turn.failed",
    error: { message: "SYNTHETIC provider failure" },
  });
  expect(message.text).toBe("SYNTHETIC partial answer");
  expect(message.status).toBe("error");
  expect(message.error).toContain("SYNTHETIC provider failure");
  expect(JSON.stringify(message)).not.toContain("private reasoning");
});

test("actual delegated operations appear as case activity without claiming completion", () => {
  const message: ChatMessage = {
    id: "SYNTHETIC",
    role: "assistant",
    text: "",
    at: "",
    status: "running",
    activity: [],
  };
  applyCliEvent(message, {
    type: "item.completed",
    item: {
      id: "SYNTHETIC-check",
      type: "collab_tool_call",
      tool: "wait",
      status: "completed",
      agents_states: { "SYNTHETIC-agent": { status: "running" } },
    },
  });
  expect(message.activity[0]).toMatchObject({
    label: "Checking review progress",
    detail: "running",
  });
  expect(message.status).toBe("running");
});

test("blocks cross-origin process launches and nonlocal hosts", () => {
  expect(() =>
    assertLocalRequest(
      new Request("http://localhost:3000/api/workspace", {
        method: "POST",
        headers: { origin: "https://example.invalid" },
      }),
    ),
  ).toThrow();
  expect(() =>
    assertLocalRequest(new Request("http://example.invalid/api/workspace")),
  ).toThrow();
  expect(() =>
    assertLocalRequest(
      new Request("http://127.0.0.1:3000/api/workspace", {
        method: "POST",
        headers: { origin: "http://127.0.0.1:3000" },
      }),
    ),
  ).not.toThrow();
});
