import { expect, test } from "@playwright/test";

test("Codex loads the OSINT skill, executes its command and displays activity", async ({
  page,
}) => {
  test.setTimeout(200_000);
  await page.goto("/");
  await expect(page.locator("body")).toContainText("Ollama");
  await expect(page.locator("body")).not.toContainText("Codex");
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC integration check: use $darknetra-osint. Read the skill and run status, tor-check, a Robin index search for Tor Project limited to 2 results, and the page command on https://example.com. Reply briefly with the actual page title and link plus the Robin provider and result count. Do not delegate, fetch index result targets or substitute web search.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.locator(".chat-message.assistant .message-text").last(),
  ).toContainText("Example Domain", { timeout: 170_000 });
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0);
  const data = await (await page.request.get("/api/workspace")).json();
  const chatId = new URL(page.url()).searchParams.get("chat");
  const message = data.chats
    .find((chat: { id: string }) => chat.id === chatId)
    .messages.at(-1);
  expect(message.status).toBe("done");
  expect(
    message.activity.some(
      (step: { label: string; status: string }) =>
        step.label === "Reading a source" && step.status === "completed",
    ),
  ).toBe(true);
  for (const label of [
    "Checking research tools",
    "Checking connectivity",
    "Checking public indexes",
    "Reading a source",
  ]) {
    expect(
      message.activity.some(
        (step: { label: string; status: string }) =>
          step.label === label &&
          (step.status === "completed" ||
            (label === "Checking connectivity" && step.status === "failed")),
      ),
    ).toBe(true);
  }
  const connectivity = message.activity.find(
    (step: { label: string }) => step.label === "Checking connectivity",
  );
  if (connectivity.status === "failed")
    expect(connectivity.result).toContain("could not be completed");
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(
    page.getByRole("complementary", { name: "Agent activity" }),
  ).toContainText("Reading a source");
  expect(
    await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
  ).toBe("rgb(20, 22, 21)");
  await page.screenshot({
    path: "test-results/cli-skill.png",
    fullPage: true,
    animations: "disabled",
  });
});

test("real CLI replies, resumes the selected chat, and keeps cases separate", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  const stamp = Date.now();
  const word = `SYNTHETIC_AMBER_${stamp}`;
  await page.goto("/");
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  await page
    .getByLabel("Case title", { exact: true })
    .fill(`SYNTHETIC CLI ${stamp}`);
  await page
    .getByLabel("Case notes", { exact: true })
    .fill("SYNTHETIC conversation test. No research is required.");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create case", exact: true })
    .click();
  await expect(page).toHaveURL(/case=/);
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      `Remember the word ${word}. Reply with exactly that word. Do not use tools.`,
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.locator(".chat-message.assistant .message-text").last(),
  ).toContainText(word, { timeout: 90_000 });
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0);
  const firstUrl = page.url();
  const firstId = new URL(firstUrl).searchParams.get("chat");
  const before = await (await page.request.get("/api/workspace")).json();
  const sessionId = before.chats.find(
    (chat: { id: string }) => chat.id === firstId,
  ).sessionId;
  expect(sessionId).toBeTruthy();
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "What word did I ask you to remember? Reply with exactly that word, and do not use tools.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".chat-message.assistant")).toHaveCount(2);
  await expect(
    page.locator(".chat-message.assistant .message-text").last(),
  ).toContainText(word, { timeout: 90_000 });
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".chat-message.assistant")).toHaveCount(2);
  const after = await (await page.request.get("/api/workspace")).json();
  expect(
    after.chats.find((chat: { id: string }) => chat.id === firstId).sessionId,
  ).toBe(sessionId);
  await page
    .getByRole("button", { name: "Toggle agent activity", exact: true })
    .click();
  await expect(
    page.getByRole("complementary", { name: "Agent activity" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/cli-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByRole("button", { name: "Close activity", exact: true })
    .click();
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  await page
    .getByLabel("Case title", { exact: true })
    .fill(`SYNTHETIC separate case ${stamp}`);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create case", exact: true })
    .click();
  await expect(page.locator(".chat-message")).toHaveCount(0);
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC test: reply with the word I asked you to remember earlier in THIS conversation. If I have not supplied one in this conversation, reply exactly UNKNOWN. Do not use tools.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.locator(".chat-message.assistant .message-text").last(),
  ).toContainText("UNKNOWN", { timeout: 90_000 });
  await expect(page.locator(".conversation-content")).not.toContainText(word);
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("complementary", { name: "Workspace navigation" }),
  ).not.toBeInViewport();
  await page.screenshot({
    path: "test-results/cli-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(failures).toEqual([]);
});

test("stopping a CLI reply persists its stopped state", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC cancellation check. Explain fractions with twenty detailed worked examples. Do not use tools.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page).toHaveURL(/chat=/);
  await page.getByRole("button", { name: "Stop reply", exact: true }).click();
  await expect(
    page
      .locator(".chat-message.assistant")
      .getByText("Stopped", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0);
  await page.reload();
  await expect(
    page
      .locator(".chat-message.assistant")
      .getByText("Stopped", { exact: true }),
  ).toBeVisible();
});
