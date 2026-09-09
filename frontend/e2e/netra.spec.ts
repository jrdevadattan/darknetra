import { expect, test } from "@playwright/test";
import type { Chat, WorkspaceData } from "../lib/chat-types";

test("the eye selects Netra for the next message and works on mobile", async ({
  page,
}) => {
  let sentMode = "";
  await page.route("**/api/chat/*", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    sentMode = route.request().postDataJSON().mode;
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({
        error: "SYNTHETIC request captured without launching research.",
      }),
    });
  });
  await page.goto("/");
  const eye = page.getByRole("button", { name: "Netra mode", exact: true });
  await expect(eye).toHaveAttribute("aria-pressed", "false");
  await eye.click();
  await expect(eye).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill("SYNTHETIC scope for eye control");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect.poll(() => sentMode).toBe("netra");
  await expect(
    page.getByRole("alert").filter({ hasText: "SYNTHETIC request captured" }),
  ).toContainText("SYNTHETIC request captured");
  await eye.click();
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect.poll(() => sentMode).toBe("normal");
  await page.setViewportSize({ width: 390, height: 844 });
  await eye.click();
  await expect(eye).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/netra-eye-mobile.png",
    fullPage: true,
  });
});

test("native goal continuation and actual Netra specialists survive reload", async ({
  page,
  request,
}) => {
  test.setTimeout(300_000);
  await page.goto("/");
  await page.getByRole("button", { name: "Netra mode", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC Netra integration verification. Scope ONLY the supplied fictional records; no external requests, no actual websites, no real evidence. Source A is a supplied fictional notice dated 2026-09-08: 'SYNTHETIC site advertised a prohibited product; no completed transaction is documented.' Source B repeats Source A verbatim. Complete TWO review passes through the native goal. In the first CLI turn create the native goal, delegate the Source A review to surface_investigator and the Source B/offline Tor coverage check to darkweb_investigator. Both should read references/netra.md, give a public progress update and return their actual review. Wait for both, then END this first turn with the checkpoint SYNTHETIC FIRST PASS, leaving the goal active because corroboration remains. On the automatic continuation turn, delegate corroboration to evidence_reviewer using the two results; have it read references/netra.md and check duplication, transaction proof and the offline-only coverage. Wait for the actual reviewer result, give the final short SYNTHETIC report, and mark the native goal complete. Use these exact roles. Do not mark complete on the first turn or invent any source retrieval.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const panel = page.getByRole("complementary", {
    name: "Agent activity",
    exact: true,
  });
  await expect(panel).toBeVisible();
  await expect(
    panel.getByRole("region", { name: "Netra investigation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0, { timeout: 260_000 });
  const chatId = new URL(page.url()).searchParams.get("chat");
  const data: WorkspaceData = await (
    await request.get("/api/workspace")
  ).json();
  const chat = data.chats.find((item: Chat) => item.id === chatId)!;
  expect(chat.messages).toHaveLength(2);
  const reply = chat.messages.at(-1)!;
  expect(reply.status).toBe("done");
  expect(reply.mode).toBe("netra");
  expect(reply.netra?.status).toBe("complete");
  expect(reply.netra?.turns).toBeGreaterThanOrEqual(2);
  expect(reply.netra?.objective).toBeTruthy();
  expect(reply.netra?.tokensUsed).toBeGreaterThan(0);
  for (const name of [
    "Surface Investigator",
    "Dark Web Investigator",
    "Evidence Reviewer",
  ]) {
    const agent = reply.agents?.find((item) => item.name === name);
    expect(agent?.status, name).toBe("completed");
    expect(agent?.result, name).toBeTruthy();
  }
  expect(reply.text).toContain("SYNTHETIC");
  expect(reply.activity.some((item) => item.id === "netra-pass-2")).toBe(true);
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await page.screenshot({
    path: "test-results/netra-specialists.png",
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Netra investigation" }),
  ).toContainText("Scoped review complete");
  await page
    .getByRole("button", { name: /View run/ })
    .last()
    .click();
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(
    panel.getByText("Evidence Reviewer", { exact: true }).first(),
  ).toBeVisible();
});
