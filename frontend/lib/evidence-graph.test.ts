import { expect, test } from "vitest";
import {
  buildEvidenceGraph,
  graphOverview,
  layoutEvidenceGraph,
} from "./evidence-graph";
import type { ChatMessage } from "./chat-types";

const message: ChatMessage = {
  id: "SYNTHETIC-large-run",
  role: "assistant",
  at: "2026-09-08T10:00:00Z",
  status: "done",
  text: "SYNTHETIC [reference](https://example.com/)",
  activity: [
    ...Array.from({ length: 40 }, (_, i) => ({
      id: `SYNTHETIC-failed-${i}`,
      label: "Reading a source",
      status: "failed",
      result: `SYNTHETIC unavailable source ${i}`,
      targetUrl: `https://example.org/${i}`,
    })),
    {
      id: "SYNTHETIC-index",
      label: "Checking an index",
      status: "completed",
      sources: [
        {
          id: "url:https://example.com/",
          title: "SYNTHETIC reference",
          url: "https://example.com/",
          kind: "lead",
          status: "listed",
        },
      ],
    },
  ],
};

test("overview groups forty failed checks, preserves their details and never upgrades unverified sources", () => {
  const full = buildEvidenceGraph(message);
  const original = JSON.stringify(full);
  const overview = graphOverview(full);
  expect(overview.nodes).toHaveLength(4);
  const group = overview.nodes.find((n) => n.memberIds);
  expect(group?.memberIds).toHaveLength(40);
  expect(group?.detail).toContain("https://example.org/39");
  expect(overview.nodes.find((n) => n.source)?.status).toBe("listed");
  expect(overview.edges).toContainEqual(
    expect.objectContaining({
      source: "lead:SYNTHETIC-large-run",
      target: "url:https://example.com/",
      label: "returned reference",
    }),
  );
  expect(
    overview.edges.every(
      (e) =>
        overview.nodes.some((n) => n.id === e.source) &&
        overview.nodes.some((n) => n.id === e.target),
    ),
  ).toBe(true);
  expect(JSON.stringify(full)).toBe(original);
  expect(full.nodes.filter((n) => n.kind === "action")).toHaveLength(41);
});

test("graph rows do not overlap and lay out every step in full history", () => {
  for (const graph of [
    buildEvidenceGraph(message),
    graphOverview(buildEvidenceGraph(message)),
  ]) {
    const layout = layoutEvidenceGraph(graph);
    expect(layout.nodes).toHaveLength(graph.nodes.length);
    expect(new Set(layout.nodes.map((n) => `${n.x},${n.y}`)).size).toBe(
      graph.nodes.length,
    );
    for (const node of layout.nodes) {
      for (const other of layout.nodes.filter((n) => n.id !== node.id))
        expect(
          Math.abs(node.x - other.x) >= 220 ||
            Math.abs(node.y - other.y) >= 140,
        ).toBe(true);
    }
  }
});
