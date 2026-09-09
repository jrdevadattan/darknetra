import { expect, test } from "@playwright/test";

test("actual specialists show their names, assignments and saved results", async ({
  page,
}) => {
  test.setTimeout(200_000);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC specialist display test. Explicitly delegate two independent tasks using your actual specialist agents: research_analyst reads the darknetra-osint skill and uses its page helper once on https://example.com, returning the title and a Markdown source link; records_analyst sorts the supplied numbers 9, 2, 5, with no external research. Use those exact agent roles, request brief public progress updates, wait for both completed results, then give a brief combined answer with the page link. No other targets are in scope.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const panel = page.getByRole("complementary", { name: "Agent activity" });
  await expect(panel).toBeVisible();
  const conversation = page.getByRole("region", {
    name: "Conversation",
    exact: true,
  });
  await expect
    .poll(async () => {
      const activityBox = await panel.boundingBox();
      const conversationBox = await conversation.boundingBox();
      return (
        !!activityBox && !!conversationBox && activityBox.x < conversationBox.x
      );
    })
    .toBe(true);
  const specialists = page
    .getByRole("region", { name: "Case specialists" })
    .first();
  await expect(specialists).toBeVisible({ timeout: 120_000 });
  await expect(
    specialists.getByText("Research Analyst", { exact: true }),
  ).toBeVisible({ timeout: 60_000 });
  await expect(
    specialists.getByText("Records Analyst", { exact: true }),
  ).toBeVisible({ timeout: 60_000 });
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0, { timeout: 120_000 });
  await expect(
    page.getByRole("tab", { name: "Evidence graph", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(specialists.locator(".specialist-card")).toHaveCount(2);
  await expect(specialists.locator(".agent-status.completed")).toHaveCount(2);
  const chatId = new URL(page.url()).searchParams.get("chat");
  const data = await (await page.request.get("/api/workspace")).json();
  const message = data.chats
    .find((c: { id: string }) => c.id === chatId)
    .messages.at(-1);
  expect(
    message.agents.every((agent: { result?: string }) => !!agent.result),
  ).toBe(true);
  expect(
    message.agents.some(
      (agent: { activity?: { sources?: { url?: string }[] }[] }) =>
        agent.activity?.some((step) =>
          step.sources?.some((source) => source.url === "https://example.com/"),
        ),
    ),
  ).toBe(true);
  await expect(panel.locator(".run-timeline")).toContainText([
    "Reading a source",
  ]);
  await specialists.getByText("View specialist report").first().click();
  await expect(specialists.locator(".agent-result").first()).toBeVisible();
  await page.reload();
  await page
    .getByRole("button", { name: /View run/ })
    .last()
    .click();
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(specialists.locator(".agent-status.completed")).toHaveCount(2);
  await page.getByRole("tab", { name: "Evidence graph", exact: true }).click();
  await expect(panel.locator(".react-flow")).toHaveClass(/dark/);
  await expect(panel.locator(".evidence-canvas")).toContainText(
    "Example Domain",
  );
  await expect(
    panel.getByRole("article", { name: "Selected graph item" }),
  ).toContainText("Retrieved");
  await page
    .getByRole("button", { name: "Swap conversation and activity" })
    .click();
  await expect
    .poll(async () => {
      const activityBox = await panel.boundingBox();
      const conversationBox = await conversation.boundingBox();
      return (
        !!activityBox && !!conversationBox && activityBox.x > conversationBox.x
      );
    })
    .toBe(true);
  await page
    .getByRole("button", { name: "Expand activity", exact: true })
    .click();
  await page.screenshot({
    path: "test-results/evidence-graph.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Collapse activity", exact: true })
    .click();
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await page.screenshot({
    path: "test-results/specialist-timeline.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(panel).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Close activity", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeVisible();
});

test("cron runs with no browser open, persists results, and exposes pause and manual controls", async ({
  page,
  request,
  baseURL,
}) => {
  test.setTimeout(200_000);
  const origin = new URL(baseURL!).origin;
  const caseResponse = await request.post("/api/workspace", {
    headers: { origin },
    data: {
      type: "case",
      title: `SYNTHETIC monitoring ${Date.now()}`,
      notes: "SYNTHETIC schedule test",
    },
  });
  const caseData = await caseResponse.json();
  await page.goto(`/?case=${caseData.id}`);
  await page
    .getByRole("button", { name: "Case monitoring", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Schedule name").fill("SYNTHETIC minute check");
  await dialog
    .getByLabel("What should be checked?")
    .fill(
      "SYNTHETIC scheduler verification only. Reply with exactly SYNTHETIC_CRON_OK. Do not use external tools or delegate; no research needed.",
    );
  await dialog
    .getByRole("combobox", { name: /Repeat/ })
    .selectOption("interval");
  await dialog.getByRole("combobox", { name: "Check every" }).selectOption("1");
  await dialog.getByRole("button", { name: "Save schedule" }).click();
  await expect(
    dialog.getByText("SYNTHETIC minute check", { exact: true }),
  ).toBeVisible();
  await expect(dialog).toContainText("Scheduler active");
  const initial = await (
    await request.get(`/api/monitors?caseId=${caseData.id}`)
  ).json();
  const monitor = initial.monitors[0];
  await page.close();
  // No open page or scheduler-trigger endpoint: only read status while server cron fires.
  await expect
    .poll(
      async () => {
        const value = await (
          await request.get(`/api/monitors?caseId=${caseData.id}`)
        ).json();
        return value.monitors[0].runs.find(
          (r: { trigger: string; status: string }) =>
            r.trigger === "scheduled" && r.status === "done",
        )?.status;
      },
      { timeout: 130_000, intervals: [2000] },
    )
    .toBe("done");
  const paused = await request.post("/api/monitors", {
    headers: { origin },
    data: {
      action: "toggle",
      caseId: caseData.id,
      id: monitor.id,
      enabled: false,
    },
  });
  expect(paused.ok()).toBe(true);
  const another = await request.post("/api/workspace", {
    headers: { origin },
    data: { type: "case", title: "SYNTHETIC other case" },
  });
  const other = await another.json();
  const denied = await request.post("/api/monitors", {
    headers: { origin },
    data: { action: "run", caseId: other.id, id: monitor.id },
  });
  expect(denied.status()).toBe(404);
  const manual = await request.post("/api/monitors", {
    headers: { origin },
    data: { action: "run", caseId: caseData.id, id: monitor.id },
  });
  expect(manual.status()).toBe(202);
  await expect
    .poll(
      async () => {
        const value = await (
          await request.get(`/api/monitors?caseId=${caseData.id}`)
        ).json();
        return value.monitors[0].runs[0].status;
      },
      { timeout: 60_000, intervals: [1500] },
    )
    .toBe("done");
  const newPage = await page.context().newPage();
  await newPage.goto(`/?case=${caseData.id}`);
  await newPage
    .getByRole("button", { name: "Case monitoring", exact: true })
    .click();
  await expect(newPage.getByRole("dialog")).toContainText("Paused");
  await expect(newPage.getByRole("dialog")).toContainText("Scheduled check");
  await expect(newPage.getByRole("dialog")).toContainText("Manual check");
  await newPage.screenshot({
    path: "test-results/case-monitoring.png",
    fullPage: true,
  });
  await newPage.setViewportSize({ width: 390, height: 844 });
  await expect(
    newPage.getByRole("button", { name: "Resume", exact: true }),
  ).toBeVisible();
  expect(
    await newPage.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await newPage
    .getByRole("button", { name: "Open results", exact: true })
    .click();
  await expect(
    newPage.locator(".chat-message.assistant .message-text").last(),
  ).toContainText("SYNTHETIC_CRON_OK");
});
