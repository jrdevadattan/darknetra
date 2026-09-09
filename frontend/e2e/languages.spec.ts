import { expect, test } from "@playwright/test";
import { languages } from "../lib/languages";
import { translate } from "../lib/translations";
import type { WorkspaceData } from "../lib/chat-types";

test("all language choices update labels, persist, and fit RTL and mobile settings", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const select = page.locator("#workspace-language");
  await expect(select).toBeEnabled();
  await expect(select.locator("option")).toHaveCount(23);
  expect(await select.locator("option").allTextContents()).toEqual(
    languages.map((l) => l.name + (l.code === "en" ? "" : ` — ${l.native}`)),
  );
  for (const language of languages) {
    await select.selectOption(language.code);
    await expect(page.locator("html")).toHaveAttribute("lang", language.code);
    await expect(
      page
        .getByRole("dialog")
        .getByRole("heading", {
          name: translate(language.code, "Settings"),
          exact: true,
        }),
    ).toBeVisible();
    await expect(select).toBeEnabled();
  }
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await page.screenshot({ path: "test-results/SYNTHETIC-language-urdu.png" });
  await select.selectOption("pa");
  await expect(page.locator("html")).toHaveAttribute("lang", "pa");
  await page.reload();
  await page.getByRole("button", { name: "ਸੈਟਿੰਗਾਂ", exact: true }).click();
  await expect(select).toHaveValue("pa");
  await page.setViewportSize({ width: 390, height: 844 });
  const bounds = await select.boundingBox();
  expect(bounds).toBeTruthy();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: "test-results/SYNTHETIC-language-punjabi-mobile.png",
  });
  await select.selectOption("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("the real CLI uses the saved language and preserves the original message", async ({
  request,
  baseURL,
}) => {
  const headers = { Origin: baseURL! };
  expect(
    (
      await request.post("/api/preferences", {
        headers,
        data: { language: "hi" },
      })
    ).ok(),
  ).toBeTruthy();
  const created = await request.post("/api/workspace", {
    headers,
    data: { type: "chat" },
  });
  const chat = await created.json();
  const text =
    "SYNTHETIC language smoke test. Reply with a short greeting only. Do not use any tools or research.";
  const response = await request.post(`/api/chat/${chat.id}`, {
    headers,
    data: { text, mode: "normal" },
    timeout: 90_000,
  });
  expect(response.ok()).toBeTruthy();
  const workspace: WorkspaceData = await (
    await request.get("/api/workspace")
  ).json();
  const saved = workspace.chats.find((c) => c.id === chat.id)!;
  expect(saved.messages[0].text).toBe(text);
  const answer = saved.messages.findLast((m) => m.role === "assistant")!;
  expect(answer.status, answer.error).toBe("done");
  expect(answer.language).toBe("hi");
  expect(answer.text).toMatch(/[\u0900-\u097f]/);
  expect(
    (
      await request.post("/api/preferences", {
        headers,
        data: { language: "en" },
      })
    ).ok(),
  ).toBeTruthy();
});
