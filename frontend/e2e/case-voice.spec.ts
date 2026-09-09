import { expect, test } from "@playwright/test";

test("a failed case reference produces a plain-language answer without invented activity", async ({
  page,
}) => {
  test.setTimeout(150_000);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC training case: review https://example.invalid using the source reader. Tell me briefly whether you could establish anything from this reference. Do not search for alternatives or delegate.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const reply = page.locator(".chat-message.assistant .message-text").last();
  await expect(reply).toContainText(
    /couldn.t|could not|unable|unavailable|unverified|not accessible|cannot|can't/i,
    { timeout: 120000 },
  );
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0);
  await expect(reply).not.toContainText(
    /Codex|CLI|subagents?|Tor connectivity|OnionLand|ENOTFOUND|NETWORK_REQUIRED|POLICY_DENIED/,
  );
  await expect(
    page.locator(".chat-message.assistant .message-author"),
  ).toContainText("Lead Investigator");
  const state = await (await page.request.get("/api/workspace")).json();
  const chatId = new URL(page.url()).searchParams.get("chat");
  const message = state.chats
    .find((chat: { id: string }) => chat.id === chatId)
    .messages.at(-1);
  expect(message.status).toBe("done");
  expect(
    message.activity.some(
      (step: { label?: string; status?: string; result?: string }) =>
        step.label === "Reading a source" &&
        step.status === "failed" &&
        step.result?.includes("could not be completed"),
    ),
  ).toBe(true);
});
