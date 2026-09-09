import { expect, test } from "@playwright/test";
import { helperResult } from "../lib/run-activity";
import type { WorkspaceData } from "../lib/chat-types";

test("source review shows coverage, grounded flags and unread access gaps", async ({
  page,
  context,
}) => {
  const at = "2026-09-09T00:00:00Z",
    url = "https://example.com/SYNTHETIC/report";
  const result = helperResult(
    `node osint.mjs site-review '${url}' 3`,
    JSON.stringify({
      ok: true,
      data: {
        analysis: "site-review",
        url,
        coverage: {
          attempted: 1,
          retrieved: 1,
          failed: 0,
          skipped: 1,
          pending: 1,
          complete: false,
          stopReason: "page_limit",
        },
        pages: [
          {
            url,
            status: "retrieved",
            title: "SYNTHETIC payment reference",
            fetchedAt: at,
            text: "SYNTHETIC public payment reference, not an allegation.",
            textOffset: 0,
            textLength: 20000,
            nextOffset: 6000,
            textTruncated: true,
            startLine: 1,
            sha256: "a".repeat(64),
            findings: [
              {
                kind: "wallet",
                reviewStatus: "needs_review",
                sourceUrl: url,
                location: { line: 7, basis: "extracted text" },
                excerpt: "SYNTHETIC payment reference, not an allegation.",
              },
            ],
          },
          {
            url: "https://example.com/SYNTHETIC/login",
            title: "SYNTHETIC private section",
            status: "skipped",
            parentUrl: url,
            reason: "Access page; no login attempted.",
          },
          {
            url: "https://example.com/SYNTHETIC/next",
            title: "SYNTHETIC next page",
            status: "pending",
            parentUrl: url,
            reason: "Page limit.",
          },
        ],
      },
    }),
  );
  const fixture: WorkspaceData = {
    version: 1,
    cases: [],
    chats: [
      {
        id: "SYNTHETIC-public-review",
        title: "SYNTHETIC public review",
        caseId: null,
        createdAt: at,
        messages: [
          {
            id: "SYNTHETIC-reply",
            role: "assistant",
            at,
            status: "done",
            text: "SYNTHETIC source review with incomplete coverage.",
            activity: [
              {
                id: "SYNTHETIC-crawl",
                label: "Reviewing linked pages",
                status: "completed",
                at,
                ...result,
              },
            ],
          },
        ],
      },
    ],
  };
  await context.route("**/api/workspace", (route) =>
    route.fulfill({ json: fixture }),
  );
  await page.goto("/?chat=SYNTHETIC-public-review");
  await page.getByRole("button", { name: /View run/ }).click();
  const panel = page.getByRole("complementary", { name: "Agent activity" });
  await panel.getByRole("tab", { name: "Timeline", exact: true }).click();
  const step = panel.locator('[data-activity-id="SYNTHETIC-crawl"]');
  await step.locator("summary").click();
  await expect(step).toContainText(/1.*retrieved|1.*read/i);
  await expect(step).toContainText(/pending/i);
  await step
    .getByRole("button", { name: /SYNTHETIC payment reference/ })
    .click();
  const inspector = panel.getByRole("article", { name: "Selected graph item" });
  await expect(inspector).toContainText("Extracted-text line 7");
  await expect(inspector).toContainText("6000");
  await expect(inspector).toContainText("Needs review");
  await expect(inspector).toContainText("not an allegation");
  await page.screenshot({
    path: "test-results/SYNTHETIC-public-review.png",
    fullPage: true,
  });
  await panel.getByRole("tab", { name: "Timeline", exact: true }).click();
  await step.locator("summary").click();
  await step.getByRole("button", { name: /SYNTHETIC private section/ }).click();
  await expect(inspector).toContainText(
    "This page was not retrieved or verified",
  );
  await expect(inspector).not.toContainText("Retrieved text:");
});

test("normal CLI chat executes the new public site review and stores its coverage", async ({
  page,
  request,
}) => {
  test.setTimeout(180000);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC integration validation: review the public website https://example.com/ using the site-review CLI helper with a strict one-page limit. Report its source content and actual coverage. Stop after this one batch; do not fetch other references, run wallet lookups, create monitoring, or use private sources. This is documentation test material, not an investigation of a person.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page).toHaveURL(/[?&]chat=/);
  const id = new URL(page.url()).searchParams.get("chat");
  await expect
    .poll(
      async () => {
        const data: WorkspaceData = await (
          await request.get("/api/workspace")
        ).json();
        return (
          data.chats.find((c) => c.id === id)?.messages.at(-1)?.status ||
          "running"
        );
      },
      { timeout: 160000, intervals: [1000, 2000, 5000] },
    )
    .not.toBe("running");
  const data: WorkspaceData = await (
    await request.get("/api/workspace")
  ).json();
  const reply = data.chats.find((c) => c.id === id)!.messages.at(-1)!;
  expect(reply.status).toBe("done");
  const review = reply.activity.find((a) => a.coverage);
  expect(review?.coverage).toMatchObject({
    attempted: 1,
    retrieved: 1,
    complete: false,
  });
  expect(
    review?.sources?.some(
      (s) => s.url === "https://example.com/" && s.status === "retrieved",
    ),
  ).toBe(true);
  expect(reply.text).toMatch(/example\.com/);
});
