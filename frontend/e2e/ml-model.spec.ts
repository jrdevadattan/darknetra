import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";

test("a supplied SYNTHETIC graph reaches the real model through the CLI and persists its source", async ({
  page,
}) => {
  test.setTimeout(190_000);
  const graph = JSON.stringify({
    feature_space: "elliptic-raw-102-v1",
    features: Array.from({ length: 4 }, (_, j) =>
      Array.from({ length: 102 }, (_, i) => (i + j * 3) / 100),
    ),
    edge_index: [
      [0, 1, 2],
      [1, 2, 3],
    ],
    node_index: 2,
    synthetic: true,
    target_id: "SYNTHETIC-TX-3",
  });
  await page.goto("/");
  await page.locator("input[type=file]").setInputFiles({
    name: "SYNTHETIC-graph.json",
    mimeType: "application/json",
    buffer: Buffer.from(graph),
  });
  await expect(page.getByLabel("Attached files")).toContainText(
    "SYNTHETIC-graph.json",
  );
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC model integration check. Use the local ML model to analyse the attached transaction graph. Report the actual illicit-class probability and fixed threshold, identify the source file, and explain the result's limitation. Use only the supplied graph and local skill. Do not delegate, search or make external research requests. This is a synthetic execution test, not a real case finding.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const reply = page.locator(".chat-message.assistant .message-text").last();
  await expect(reply).toContainText(/synthetic/i, { timeout: 160_000 });
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0, { timeout: 150_000 });
  const data = await (await page.request.get("/api/workspace")).json();
  const id = new URL(page.url()).searchParams.get("chat");
  const message = data.chats
    .find((c: { id: string }) => c.id === id)
    .messages.at(-1);
  expect(message.status).toBe("done");
  const step = message.activity.find(
    (s: { label: string; sources?: unknown[] }) =>
      s.label === "Analysing a transaction graph" && s.sources?.length,
  );
  expect(step).toBeTruthy();
  expect(step.status).toBe("completed");
  expect(step.sources[0].sha256).toBe(
    createHash("sha256").update(graph).digest("hex"),
  );
  expect(step.result).toContain("0.7166666666666667");
  expect(step.result).toContain("SYNTHETIC");
  const score = Number(
    step.result.match(/Illicit-class score: ([\d.e+-]+)/)?.[1],
  );
  expect(Number.isFinite(score)).toBe(true);
  expect(score).toBeGreaterThanOrEqual(0);
  expect(score).toBeLessThanOrEqual(1);
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(
    page.getByRole("complementary", { name: "Agent activity" }),
  ).toContainText("Analysing a transaction graph");
  await page.screenshot({
    path: "test-results/ml-timeline.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Evidence graph", exact: true }).click();
  await expect(page.locator(".evidence-canvas")).toContainText(
    "SYNTHETIC-graph.json",
  );
  await page
    .locator(".evidence-canvas .react-flow__node")
    .filter({ hasText: "SYNTHETIC-graph.json" })
    .click();
  await expect(
    page.getByRole("article", { name: "Selected graph item" }),
  ).toContainText("Illicit-class score");
  await page.reload();
  const saved = await (await page.request.get("/api/workspace")).json();
  const persisted = saved.chats
    .find((c: { id: string }) => c.id === id)
    .messages.at(-1);
  expect(
    persisted.activity.find((s: { id: string }) => s.id === step.id).sources[0]
      .sha256,
  ).toBe(step.sources[0].sha256);
  await page.screenshot({ path: "test-results/ml-graph.png", fullPage: true });
});
