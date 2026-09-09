import { expect, test } from "vitest";
import {
  helperResult,
  recordActivity,
  commandTarget,
  commandLabel,
} from "./run-activity";
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

test("linked-page review keeps each retrieval separate from failed and unread references", () => {
  const data = {
    analysis: "site-review",
    url: "https://example.com/",
    text: "SYNTHETIC aggregate summary must not replace individual pages",
    coverage: {
      attempted: 3,
      retrieved: 2,
      failed: 1,
      skipped: 1,
      pending: 1,
      complete: true,
      stopReason: "page limit",
    },
    pages: [
      {
        url: "https://example.com/",
        status: "retrieved",
        title: "SYNTHETIC homepage",
        text: "SYNTHETIC home",
        fetchedAt: at,
      },
      {
        url: "https://example.com/pay",
        parentUrl: "https://example.com/",
        status: "retrieved",
        title: "SYNTHETIC payment",
        text: "SYNTHETIC payment reference",
        sha256: "a".repeat(64),
        fetchedAt: at,
        textTruncated: true,
        findings: [
          {
            kind: "payment-reference",
            reviewStatus: "needs_review",
            sourceUrl: "https://example.com/pay",
            excerpt: "SYNTHETIC payment reference",
            location: { line: 7 },
          },
          {
            kind: "wallet",
            reviewStatus: "needs_review",
            sourceUrl: "https://unrelated.example/",
            excerpt: "SYNTHETIC wrong-page flag",
            location: { line: 8 },
          },
          {
            kind: "wallet",
            reviewStatus: "needs_review",
            sourceUrl: "https://example.com/pay",
            excerpt: "SYNTHETIC no-location flag",
          },
        ],
      },
      {
        url: "https://example.com/failed",
        parentUrl: "https://example.com/",
        status: "failed",
        reason: "Timed out",
        text: "SYNTHETIC unread content",
      },
      {
        url: "https://example.com/login",
        status: "skipped",
        reason: "Access required",
        findings: [
          {
            kind: "wallet",
            sourceUrl: "https://example.com/login",
            excerpt: "SYNTHETIC unread claim",
            location: { line: 1 },
            reviewStatus: "needs_review",
          },
        ],
      },
      {
        url: "https://example.com/later",
        status: "pending",
        reason: "Page limit",
      },
      {
        url: "https://user:secret@example.com/",
        status: "retrieved",
        text: "SYNTHETIC invalid URL",
      },
    ],
  };
  const result = helperResult(
    "node osint.mjs site-review https://example.com/",
    JSON.stringify({ ok: true, data }),
  );
  expect(result.sources).toHaveLength(5);
  expect(result.sources?.map((source) => source.status)).toEqual([
    "retrieved",
    "retrieved",
    "unavailable",
    "referenced",
    "referenced",
  ]);
  expect(result.sources?.[1]).toMatchObject({
    at,
    sha256: "a".repeat(64),
    reviewNeeded: true,
    parentId: "url:https://example.com/",
    parentRelation: "links to",
  });
  expect(result.sources?.[1].excerpt).toContain("Extracted-text line 7");
  expect(result.sources?.[1].excerpt).toContain(
    "does not establish wrongdoing",
  );
  expect(result.sources?.[1].excerpt).toContain("truncated");
  expect(JSON.stringify(result.sources)).not.toMatch(
    /wrong-page flag|no-location flag|unread content|unread claim|secret|aggregate summary/,
  );
  expect(result.sources?.[2].excerpt).toContain("Timed out");
  expect(result.coverage?.complete).toBe(false);
  expect(result.result).toContain(
    "2 retrieved, 1 failed, 1 skipped, 1 pending",
  );
  expect(result.result).toContain("not proof of complete website coverage");
  const message = sample();
  message.activity = [
    {
      id: "SYNTHETIC-review",
      label: "Reviewing linked pages",
      status: "completed",
      ...result,
    },
  ];
  const graph = buildEvidenceGraph(message);
  expect(graph.edges).toContainEqual(
    expect.objectContaining({
      source: "url:https://example.com/",
      target: "url:https://example.com/pay",
      label: "links to",
    }),
  );
  expect(
    graph.edges
      .filter((edge) => edge.target === "url:https://example.com/failed")
      .map((edge) => edge.label),
  ).toContain("retrieval failed");
  expect(
    graph.edges
      .filter((edge) => edge.target === "url:https://example.com/login")
      .map((edge) => edge.label),
  ).toEqual(["not retrieved"]);
});

test("review commands have readable labels and only supported URL commands expose a target", () => {
  expect(
    commandTarget("node osint.mjs site-review 'https://example.com/'"),
  ).toBe("https://example.com/");
  expect(
    commandTarget(
      "node osint.mjs page-section 'https://example.com/long' 6000",
    ),
  ).toBe("https://example.com/long");
  expect(commandLabel("node osint.mjs site-review https://example.com/")).toBe(
    "Reviewing linked pages",
  );
  expect(commandLabel("node osint.mjs wallet-review bitcoin SYNTHETIC")).toBe(
    "Reviewing public transactions",
  );
  expect(
    commandTarget("node osint.mjs wallet-review bitcoin SYNTHETIC"),
  ).toBeUndefined();
});

test("site-review cap notices survive normalization even when every displayed page succeeded", () => {
  const data = {
    analysis: "site-review",
    coverage: {
      attempted: 4,
      retrieved: 4,
      failed: 0,
      skipped: 0,
      pending: 0,
      inventoriesTruncated: 2,
      frontierTruncated: true,
      outputTruncated: true,
      omittedRecords: 3,
    },
    pages: [
      {
        url: "https://example.com/SYNTHETIC",
        status: "retrieved",
        fetchedAt: at,
        text: "SYNTHETIC visible excerpt",
        findings: [],
        findingsTruncated: true,
      },
    ],
  };
  const result = helperResult(
    "node osint.mjs site-review https://example.com/",
    JSON.stringify({ ok: true, data }),
  );
  expect(result.coverage).toMatchObject({
    retrieved: 4,
    inventoriesTruncated: 2,
    frontierTruncated: true,
    outputTruncated: true,
    omittedRecords: 3,
  });
  expect(result.sources).toHaveLength(1);
  expect(result.sources?.[0]).toMatchObject({
    status: "retrieved",
    reviewNeeded: true,
  });
  expect(result.sources?.[0].excerpt).toContain("Review flags are truncated");
  expect(result.result).toContain("2 page link inventories exceeded");
  expect(result.result).toContain("discovered-link list reached its limit");
  expect(result.result).toContain("3 page records were omitted");
  expect(result.result).toContain(
    "Coverage counts include records absent from this display",
  );
  const page = helperResult(
    command,
    JSON.stringify({
      ok: true,
      data: { ...data.pages[0], findingsTruncated: true },
    }),
  );
  expect(page.sources?.[0].excerpt).toContain("Review flags are truncated");
});

test("wallet records preserve exact units and API provenance without marking explorer links retrieved", () => {
  const api = "https://example.com/api/address/SYNTHETIC/txs";
  const txid = "a".repeat(64);
  const amount = (satoshis: string, btc: string) => ({ satoshis, btc });
  const data = {
    analysis: "wallet_review",
    network: "bitcoin",
    address: "SYNTHETIC",
    url: api,
    explorerUrl: "https://example.com/address/SYNTHETIC",
    text: "SYNTHETIC bounded public transaction review; ML input requirements remain unmet.",
    sources: [{ url: api, fetchedAt: at, contentSha256: "b".repeat(64) }],
    transactions: [
      {
        txid,
        url: `https://example.com/tx/${txid}`,
        sourceUrl: api,
        status: { confirmed: true, confirmations: 7 },
        addressReceived: amount("123456789", "1.23456789"),
        addressSpent: amount("200000000", "2.00000000"),
        addressNet: amount("-76543211", "-0.76543211"),
        fee: amount("500", "0.00000500"),
        inputs: [
          {
            address: "SYNTHETIC-input",
            amount: amount("200000000", "2.00000000"),
          },
        ],
        outputs: [
          {
            address: "SYNTHETIC-output",
            amount: amount("123456789", "1.23456789"),
          },
        ],
      },
      {
        txid: "c".repeat(64),
        url: "https://example.com/uncited",
        sourceUrl: "https://unfetched.example/api/tx",
        status: { confirmed: true },
      },
    ],
  };
  const result = helperResult(
    "node osint.mjs wallet-review bitcoin SYNTHETIC",
    JSON.stringify({ ok: true, data }),
  );
  expect(result.sources).toHaveLength(3);
  expect(result.sources?.[0]).toMatchObject({
    url: api,
    status: "retrieved",
    at,
    sha256: "b".repeat(64),
  });
  expect(result.sources?.[1].status).toBe("referenced");
  const tx = result.sources?.[2];
  expect(tx).toMatchObject({ status: "referenced", parentId: `url:${api}` });
  expect(tx?.excerpt).toContain("1.23456789 BTC (123456789 satoshis)");
  expect(tx?.excerpt).toContain("-0.76543211 BTC (-76543211 satoshis)");
  expect(tx?.excerpt).toContain("7 confirmations");
  expect(tx?.excerpt).toContain(api);
  expect(tx?.excerpt).toContain("explorer page was not retrieved");
  expect(tx?.excerpt).toContain(
    "does not establish a sender-to-recipient transfer",
  );
  expect(JSON.stringify(result)).not.toContain("uncited");
  expect(result.result).toContain(
    "1 API source(s) retrieved; 1 transaction reference(s)",
  );
});

test("wallet API failures distinguish unavailable reads from retrieved but unusable data", () => {
  const data = {
    analysis: "wallet_review",
    text: "SYNTHETIC failed reads leave gaps.",
    sources: [{ url: "https://example.com/api/read", fetchedAt: at }],
    failures: [
      {
        url: "https://example.com/api/read",
        code: "INVALID_TRANSACTION",
        message: "SYNTHETIC raw error",
      },
      { url: "https://example.com/api/unread", code: "NETWORK_FAILED" },
    ],
  };
  const result = helperResult(
    "node osint.mjs wallet-review bitcoin SYNTHETIC",
    JSON.stringify({ ok: true, data }),
  );
  expect(result.sources).toHaveLength(2);
  expect(result.sources?.[0]).toMatchObject({
    status: "retrieved",
    reviewNeeded: true,
  });
  expect(result.sources?.[1]).toMatchObject({
    status: "unavailable",
    reviewNeeded: true,
  });
  expect(result.sources?.[0].excerpt).toContain("INVALID_TRANSACTION");
  expect(JSON.stringify(result)).not.toContain("raw error");
});

test("single-page sections preserve their text location, extraction limits and source-specific review flags", () => {
  const data = {
    url: "https://example.com/SYNTHETIC-long",
    title: "SYNTHETIC page section",
    fetchedAt: at,
    text: "SYNTHETIC payment reference in this section",
    textOffset: 6000,
    textLength: 40000,
    nextOffset: 18000,
    startLine: 42,
    sha256: "c".repeat(64),
    hashScope: "decoded response body",
    extraction: {
      renderedJavascript: false,
      javascriptLikely: true,
      warnings: ["SYNTHETIC dynamic-content warning"],
      completeSite: false,
    },
    findings: [
      {
        kind: "payment-reference",
        sourceUrl: "https://example.com/SYNTHETIC-long",
        excerpt: "SYNTHETIC payment reference",
        location: { line: 42, offset: 6000, basis: "extracted text" },
        reviewStatus: "needs_review",
      },
    ],
  };
  const result = helperResult(
    "node osint.mjs page-section https://example.com/SYNTHETIC-long 6000",
    JSON.stringify({ ok: true, data }),
  );
  const source = result.sources?.[0];
  expect(source).toMatchObject({
    status: "retrieved",
    sha256: "c".repeat(64),
    reviewNeeded: true,
    id: "url:https://example.com/SYNTHETIC-long:text-offset:6000",
    parentId: "url:https://example.com/SYNTHETIC-long",
    parentRelation: "has text section",
  });
  expect(source?.excerpt).toContain("offset: 6000 of 40000");
  expect(source?.excerpt).toContain("More text is available at offset 18000");
  expect(source?.excerpt).toContain("Extracted-text line 42");
  expect(source?.excerpt).toContain("JavaScript was not executed");
  expect(source?.excerpt).toContain("SYNTHETIC dynamic-content warning");
  expect(source?.excerpt).toContain("SHA-256 scope: decoded response body");
  const message = sample();
  message.activity = [
    {
      id: "SYNTHETIC-first-section",
      label: "Reading a source",
      status: "completed",
      ...helperResult(
        command,
        JSON.stringify({
          ok: true,
          data: { ...data, textOffset: 0, text: "SYNTHETIC first section" },
        }),
      ),
    },
    {
      id: "SYNTHETIC-next-section",
      label: "Reading a source section",
      status: "completed",
      ...result,
    },
  ];
  const graph = buildEvidenceGraph(message);
  expect(
    graph.nodes.filter((node) => node.source?.url === data.url),
  ).toHaveLength(2);
  expect(
    graph.nodes.find((node) => node.id === source?.parentId)?.detail,
  ).toContain("SYNTHETIC first section");
  expect(graph.nodes.find((node) => node.id === source?.id)?.detail).toContain(
    "SYNTHETIC payment reference in this section",
  );
  expect(graph.edges).toContainEqual(
    expect.objectContaining({
      source: source?.parentId,
      target: source?.id,
      label: "has text section",
    }),
  );
});

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
