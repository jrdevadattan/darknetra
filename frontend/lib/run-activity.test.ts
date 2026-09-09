import { expect, test } from "vitest";
import { helperResult, recordActivity, commandTarget } from "./run-activity";
import { buildEvidenceGraph } from "./evidence-graph";
import { applyAgentRecords } from "./agents";
import type { Activity, ChatMessage } from "./chat-types";

const at = "2026-09-08T10:00:00.000Z";
const sample = (): ChatMessage => ({
  id: "SYNTHETIC-run",
  role: "assistant",
  text: "",
  at,
  status: "running",
  activity: [],
});
const output = JSON.stringify({
  ok: true,
  data: {
    url: "https://example.com/",
    title: "SYNTHETIC source",
    text: "SYNTHETIC public document",
    fetchedAt: at,
  },
});
const command =
  "node .agents/skills/darknetra-osint/scripts/osint.mjs page 'https://example.com/'";

test("metadata findings reach activity and source details with their hash", () => {
  const data = {
    analysis: "metadata",
    file: "SYNTHETIC.png",
    sha256: "a".repeat(64),
    text: "Metadata checked. PNG:Description: SYNTHETIC case fixture. No capture time or GPS tags found.",
  };
  const result = helperResult(
    "node osint.mjs metadata SYNTHETIC.png",
    JSON.stringify({ ok: true, data }),
  );
  expect(result.result).toContain("PNG:Description");
  expect(result.sources?.[0]).toMatchObject({
    sha256: data.sha256,
    excerpt: data.text,
    status: "analysed",
  });
  const remote = helperResult(
    "node osint.mjs image-metadata https://example.com/SYNTHETIC.png",
    JSON.stringify({
      ok: true,
      data: {
        ...data,
        file: undefined,
        url: "https://example.com/SYNTHETIC.png",
        fetchedAt: at,
      },
    }),
  );
  expect(remote.result).toContain("PNG:Description");
  expect(remote.sources?.[0]).toMatchObject({
    sha256: data.sha256,
    status: "analysed",
    at,
  });
});

test("metadata failures remain unverified and explain the failed extraction", () => {
  const result = helperResult(
    "node osint.mjs metadata SYNTHETIC.png",
    JSON.stringify({
      ok: false,
      error: {
        code: "METADATA_UNREADABLE",
        message: "The supplied bytes could not be parsed.",
      },
    }),
  );
  expect(result.result).toContain("could not be parsed");
  expect(result.result).toContain("unverified");
  expect(result.sources).toBeUndefined();
});

test("captured favicon metadata reaches graph sources without allowing remote image URLs or SVG", () => {
  const favicon = "data:image/png;base64,U1lOVEhFVElD";
  const page = JSON.parse(output);
  page.data.favicon = favicon;
  const result = helperResult(command, JSON.stringify(page));
  const message = sample();
  message.activity = [
    {
      id: "SYNTHETIC-page",
      label: "Reading a source",
      status: "completed",
      ...result,
    },
  ];
  expect(
    buildEvidenceGraph(message).nodes.find((n) => n.kind === "source")?.source
      ?.favicon,
  ).toBe(favicon);
  for (const invalid of [
    "https://example.com/icon.png",
    "data:image/svg+xml;base64,U1lOVEhFVElD",
    "data:image/png;base64," + "a".repeat(44000),
  ]) {
    page.data.favicon = invalid;
    expect(
      helperResult(command, JSON.stringify(page)).sources?.[0].favicon,
    ).toBeUndefined();
  }
});

test("active website metadata identifies the command target without inventing source records", () => {
  expect(commandTarget(command)).toBe("https://example.com/");
  expect(commandTarget("cat https://example.com")).toBeUndefined();
  expect(
    commandTarget("osint.mjs robin 'https://example.com'"),
  ).toBeUndefined();
  const message = sample();
  message.activity = [
    {
      id: "SYNTHETIC-pending",
      label: "Reading a source",
      status: "running",
      targetUrl: commandTarget(command),
    },
  ];
  expect(buildEvidenceGraph(message).sourceCount).toBe(0);
});

test("source records come only from supported helper JSON, never arbitrary output or failures", () => {
  expect(helperResult("cat credentials", output)).toEqual({});
  expect(helperResult(command, "SYNTHETIC secret")).toEqual({});
  const result = helperResult(command, output);
  expect(result.sources).toMatchObject([
    {
      title: "SYNTHETIC source",
      status: "retrieved",
      url: "https://example.com/",
    },
  ]);
  const failed = helperResult(
    command,
    JSON.stringify({
      ok: false,
      error: { code: "NETWORK_REQUIRED", message: "SYNTHETIC secret" },
    }),
  );
  expect(failed.sources).toBeUndefined();
  expect(failed.result).toContain("does not establish");
  expect(failed.result).not.toContain("secret");
  expect(
    helperResult(
      command,
      JSON.stringify({
        ok: true,
        data: { url: "https://user:secret@example.com/", text: "no" },
      }),
    ).sources,
  ).toHaveLength(0);
});

test("native child item records keep actions ordered and bounded to the correct child, without hidden content", () => {
  const message = sample();
  const event = (item: unknown, thread_id = "SYNTHETIC-child") => ({
    type: "event_msg",
    timestamp: at,
    payload: {
      type: "item_completed",
      thread_id,
      turn_id: "child-turn",
      started_at_ms: Date.parse(at),
      item,
    },
  });
  const records = [
    {
      type: "event_msg",
      timestamp: at,
      payload: {
        type: "task_started",
        turn_id: "child-turn",
        started_at: Date.parse(at) / 1000,
      },
    },
    event({
      type: "AgentMessage",
      id: "update",
      phase: "commentary",
      content: [
        { type: "Text", text: "SYNTHETIC checking source" },
        { type: "Encrypted", text: "SYNTHETIC secret" },
      ],
    }),
    event({
      type: "Reasoning",
      id: "hidden",
      content: [{ type: "Text", text: "SYNTHETIC private reasoning" }],
    }),
    event(
      {
        type: "CommandExecution",
        id: "other",
        command: ["cat unrelated"],
        aggregated_output: output,
        status: "completed",
      },
      "SYNTHETIC-other-case",
    ),
    event({
      type: "CommandExecution",
      id: "page",
      command: ["/bin/bash", "-lc", command],
      aggregated_output: output,
      exit_code: 0,
      status: "completed",
    }),
    {
      type: "event_msg",
      timestamp: at,
      payload: {
        type: "task_complete",
        turn_id: "child-turn",
        last_agent_message: "SYNTHETIC report",
      },
    },
  ];
  applyAgentRecords(message, "SYNTHETIC-child", { timestamp: at }, records);
  applyAgentRecords(message, "SYNTHETIC-child", { timestamp: at }, records);
  const agent = message.agents![0];
  expect(agent.activity).toHaveLength(2);
  expect(agent.activity![1].sources?.[0].url).toBe("https://example.com/");
  expect(agent.status).toBe("completed");
  expect(JSON.stringify(message)).not.toMatch(
    /secret|private reasoning|unrelated/,
  );
  const old = sample();
  old.at = "2026-09-08T11:00:00Z";
  applyAgentRecords(old, "SYNTHETIC-child", { timestamp: at }, records);
  expect(old.agents).toBeUndefined();
});

test("graph links shared sources, actual child checks, attachments and citations without upgrading index leads", () => {
  const message = sample();
  message.status = "done";
  message.text =
    "SYNTHETIC [source](https://example.com/) and [unread reference](https://example.org/).";
  message.agents = [
    {
      id: "SYNTHETIC-child",
      name: "Research Analyst",
      task: "SYNTHETIC check",
      status: "completed",
      result: "SYNTHETIC report",
      activity: [
        {
          id: "page",
          label: "Reading a source",
          status: "completed",
          ...helperResult(command, output),
        },
      ],
    },
  ];
  message.activity = [
    {
      id: "index",
      label: "Checking public indexes",
      status: "completed",
      ...helperResult(
        command,
        JSON.stringify({
          ok: true,
          data: {
            source: "https://example.net/search",
            provider: "SYNTHETIC",
            hits: [
              {
                url: "https://example.org/",
                title: "SYNTHETIC unverified lead",
              },
            ],
          },
        }),
      ),
    },
  ];
  const graph = buildEvidenceGraph(message, [
    { name: "SYNTHETIC.txt", label: "SYNTHETIC file", size: 42 },
  ]);
  expect(
    graph.nodes.filter((n) => n.id === "url:https://example.com/"),
  ).toHaveLength(1);
  expect(
    graph.nodes.find((n) => n.id === "url:https://example.org/")?.status,
  ).toBe("listed");
  expect(graph.nodes.find((n) => n.id === "file:SYNTHETIC.txt")?.status).toBe(
    "supplied",
  );
  expect(graph.edges).toContainEqual(
    expect.objectContaining({
      source: "url:https://example.net/search",
      target: "url:https://example.org/",
      label: "lists",
    }),
  );
  expect(graph.edges).toContainEqual(
    expect.objectContaining({
      source: "url:https://example.com/",
      target: "report:SYNTHETIC-run",
      label: "cited in report",
    }),
  );
  expect(
    graph.edges.every(
      (e) =>
        graph.nodes.some((n) => n.id === e.source) &&
        graph.nodes.some((n) => n.id === e.target),
    ),
  ).toBe(true);
  expect(buildEvidenceGraph(sample()).sourceCount).toBe(0);
});

test("timeline preserves start time on completion and signals bounded history", () => {
  const list: Activity[] = [];
  recordActivity(list, {
    id: "SYNTHETIC",
    label: "Check",
    status: "running",
    at,
  });
  recordActivity(list, {
    id: "SYNTHETIC",
    label: "Check",
    status: "completed",
    at: "2026-09-08T10:01:00Z",
  });
  expect(list[0].at).toBe(at);
  for (let i = 0; i < 299; i++)
    recordActivity(list, {
      id: `SYNTHETIC-${i}`,
      label: "Check",
      status: "completed",
      at,
    });
  expect(
    recordActivity(list, {
      id: "SYNTHETIC-last",
      label: "Check",
      status: "completed",
      at,
    }),
  ).toBe(true);
  expect(list).toHaveLength(300);
});
