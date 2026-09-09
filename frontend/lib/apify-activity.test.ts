import { test, expect } from "vitest";
import { commandLabel, commandTarget, helperResult } from "./run-activity";
import { applyCliEvent } from "./codex";
import type { ChatMessage } from "./chat-types";

test("backup reads retain the actual source, and MCP catalog search is activity rather than case evidence", () => {
  const command =
    "node osint.mjs apify-page 'https://example.com/' explicit-request";
  expect(commandTarget(command)).toBe("https://example.com/");
  expect(commandLabel(command)).toBe("Reading a source with the backup reader");
  const data = {
    role: "backup",
    provider: "apify",
    url: "https://example.com/",
    title: "SYNTHETIC source",
    text: "SYNTHETIC public page. Source statements remain unverified.",
    fetchedAt: "2026-09-08T10:00:00Z",
  };
  expect(
    helperResult(command, JSON.stringify({ ok: true, data })).sources?.[0],
  ).toMatchObject({ url: data.url, status: "retrieved", excerpt: data.text });
  const message: ChatMessage = {
    id: "SYNTHETIC",
    role: "assistant",
    text: "",
    status: "running",
    at: "",
    activity: [],
  };
  applyCliEvent(message, {
    type: "item.completed",
    item: {
      id: "SYNTHETIC-search",
      type: "mcp_tool_call",
      server: "apify_catalog",
      tool: "search-actors",
      status: "completed",
    },
  });
  expect(message.activity[0].label).toBe("Finding backup scrapers");
  expect(message.activity[0].sources).toBeUndefined();
});
