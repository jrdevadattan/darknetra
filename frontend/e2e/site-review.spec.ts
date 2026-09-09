import { expect, test } from "@playwright/test";
import type { WorkspaceData } from "../lib/chat-types";

test("normal chat retrieves a supplied public page and follows its recorded link", async ({
  page,
  request,
}) => {
  test.setTimeout(180_000);
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "SYNTHETIC integration check, normal mode: review https://example.com/ and follow at most one relevant link from that page. Stop after two page reads. Report what each retrieved source actually says and the coverage. These public documentation pages are test material, not case evidence. Do not use Telegram or other private sources.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page).toHaveURL(/[?&]chat=/);
  const chatId = new URL(page.url()).searchParams.get("chat");
  await expect
    .poll(
      async () => {
        const state: WorkspaceData = await (
          await request.get("/api/workspace")
        ).json();
        return (
          state.chats.find((chat) => chat.id === chatId)?.messages.at(-1)
            ?.status || "running"
        );
      },
      { timeout: 160_000, intervals: [1000, 2000, 5000] },
    )
    .not.toBe("running");
  const data: WorkspaceData = await (
    await request.get("/api/workspace")
  ).json();
  const reply = data.chats.find((chat) => chat.id === chatId)!.messages.at(-1)!;
  expect(reply.status).toBe("done");
  expect(reply.mode).toBe("normal");
  const reads = reply.activity
    .flatMap((activity) => activity.sources || [])
    .filter(
      (source) => source.status === "retrieved" && source.kind === "page",
    );
  expect(reads.some((source) => source.url === "https://example.com/")).toBe(
    true,
  );
  expect(
    reads.some(
      (source) =>
        source.url && new URL(source.url).hostname.endsWith("iana.org"),
    ),
  ).toBe(true);
  expect(
    reply.activity.some(
      (activity) => activity.label === "Reading configured Telegram messages",
    ),
  ).toBe(false);
  expect(reply.text).toMatch(/https?:\/\/.*iana\.org/);
});
