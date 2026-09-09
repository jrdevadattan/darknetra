import { expect, test } from "vitest";
import { boardSnapshot, boardPrompt, boardPlan } from "./case-board";
import type { WorkspaceData } from "./chat-types";

const data: WorkspaceData = {
  version: 1,
  cases: [
    {
      id: "a",
      title: "SYNTHETIC A",
      notes: "SYNTHETIC scope",
      createdAt: "2026-09-08",
    },
    {
      id: "b",
      title: "SYNTHETIC B",
      notes: "OTHER CASE SECRET",
      createdAt: "2026-09-08",
    },
  ],
  chats: [
    {
      id: "chat-a",
      caseId: "a",
      title: "SYNTHETIC review",
      createdAt: "2026-09-08",
      messages: [
        {
          id: "ma",
          role: "assistant",
          text: "SYNTHETIC finding with a source.",
          at: "2026-09-08",
          status: "done",
          activity: [
            {
              id: "step",
              label: "Reading",
              status: "completed",
              sources: [
                {
                  id: "url:https://example.com/",
                  url: "https://example.com/",
                  title: "SYNTHETIC source",
                  kind: "page",
                  status: "retrieved",
                  excerpt: "SYNTHETIC excerpt",
                  sha256: "a".repeat(64),
                },
              ],
            },
          ],
        },
      ],
    },
    {
      id: "chat-b",
      caseId: "b",
      title: "OTHER CASE SECRET",
      createdAt: "2026-09-08",
      messages: [
        {
          id: "mb",
          role: "assistant",
          text: "OTHER CASE SECRET",
          at: "2026-09-08",
          status: "done",
          activity: [],
        },
      ],
    },
  ],
};

test("case board captures only selected-case material and keeps its provenance", () => {
  const board = boardSnapshot(data, "a");
  expect(JSON.stringify(board)).not.toContain("OTHER CASE");
  expect(board.cards.find((c) => c.url)).toMatchObject({
    title: "SYNTHETIC source",
    chatId: "chat-a",
    messageId: "ma",
    sha256: "a".repeat(64),
  });
  expect(boardPrompt(board)).not.toContain("OTHER CASE");
  expect(boardPrompt(board)).toContain("suggestions");
  expect(() => boardSnapshot(data, "missing")).toThrow("Case not found");
});

test("assistant board plans cannot invent cards or promote a suggested connection", () => {
  const board = boardSnapshot(data, "a");
  const [a, b] = board.cards;
  const plan = boardPlan(
    JSON.stringify({
      order: [b.id, "invented", b.id],
      notes: [
        { cardId: "invented", text: "bad" },
        { cardId: a.id, text: "SYNTHETIC suggestion" },
      ],
      links: [
        {
          from: a.id,
          to: b.id,
          label: "SYNTHETIC relationship",
          reason: "Check the original source",
        },
        { from: a.id, to: "invented", label: "bad" },
      ],
    }),
    board,
  );
  expect(plan.order).toEqual([b.id, a.id]);
  expect(plan.notes).toHaveLength(1);
  expect(plan.links).toHaveLength(1);
  expect(plan.links[0].suggested).toBe(true);
  expect(boardPlan("unreadable output", board).valid).toBe(false);
});

test("large boards disclose incomplete coverage and bound the CLI context", () => {
  const many = structuredClone(data);
  many.chats[0].messages[0].activity[0].sources = Array.from(
    { length: 80 },
    (_, i) => ({
      id: `source:${i}`,
      url: `https://example.com/SYNTHETIC/${i}`,
      title: `SYNTHETIC ${i}`,
      kind: "page",
      status: "retrieved",
      excerpt: "SYNTHETIC ".repeat(500),
    }),
  );
  const board = boardSnapshot(many, "a");
  expect(board.truncated).toBe(true);
  expect(board.cards.length).toBeLessThanOrEqual(36);
  expect(boardPrompt(board).length).toBeLessThan(32000);
});

test("image board context prioritises actual metadata values over repeated boilerplate", () => {
  const fixture = structuredClone(data);
  fixture.chats[0].messages[0].activity[0].sources![0].excerpt =
    "Metadata checked.\n" +
    "SYNTHETIC review limitation. ".repeat(30) +
    "\nExifIFD:DateTimeOriginal: 2020:01:02 03:04:05+05:30\nGPS:GPSLatitude: 0 N\nGPS:GPSLongitude: 0 E\nIFD0:Make: SYNTHETIC camera";
  const prompt = boardPrompt(boardSnapshot(fixture, "a"));
  expect(prompt).toContain("2020:01:02 03:04:05+05:30");
  expect(prompt).toContain("GPSLongitude: 0 E");
  expect(prompt).toContain("Unverified embedded metadata");
});
