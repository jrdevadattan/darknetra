import { test, expect } from "@playwright/test";

test("the assistant searches the live Apify MCP catalog through its CLI skill", async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC integration check. Use the local OSINT skill command apify-search with query 'website content' and limit 1 to search the live Apify MCP catalog, then use apify-actor for the returned Actor's required inputs and pricing. Report the name and required fields. This is catalog verification only. Do not run any Actor, read source websites, delegate, create monitors or inspect other files. Keep Apify a backup.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const reply = page.locator(".chat-message.assistant .message-text").last();
  await expect(reply).toContainText(/website.content.crawler/i, {
    timeout: 150000,
  });
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0, { timeout: 150000 });
  const data = await (await page.request.get("/api/workspace")).json();
  const id = new URL(page.url()).searchParams.get("chat");
  const message = data.chats
    .find((c: { id: string }) => c.id === id)
    .messages.at(-1);
  expect(message.status).toBe("done");
  const search = message.activity.find(
    (a: { label: string }) => a.label === "Finding backup scrapers",
  );
  const details = message.activity.find(
    (a: { label: string }) => a.label === "Reviewing a backup scraper",
  );
  expect(search).toMatchObject({ status: "completed", sources: [] });
  expect(search.result).toContain("candidate");
  expect(details).toMatchObject({ status: "completed", sources: [] });
  expect(details.result).toContain("Input and pricing");
  expect(JSON.stringify(message)).not.toContain("apify_api_");
});
