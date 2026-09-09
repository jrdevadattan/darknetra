import { expect, test } from "@playwright/test";
import type { Case, Chat, WorkspaceData } from "../lib/chat-types";

test("archive, search, review and restore chats; case folder controls persist", async ({
  page,
  request,
  baseURL,
}) => {
  const post = async (body: unknown) => {
    const response = await request.post("/api/workspace", {
      headers: { Origin: baseURL! },
      data: body,
    });
    expect(response.ok()).toBe(true);
    return response.json();
  };
  const caseA: Case = await post({
    type: "case",
    title: "SYNTHETIC archive review",
    notes: "SYNTHETIC fixture",
  });
  const caseB: Case = await post({
    type: "case",
    title: "SYNTHETIC second folder",
    notes: "",
  });
  const chat: Chat = await post({ type: "chat", caseId: caseA.id });
  const personal: Chat = await post({ type: "chat" });
  await page.addInitScript(() => localStorage.setItem("theme", "light"));
  await page.goto(`/?case=${caseA.id}&chat=${chat.id}`);
  const nav = page.getByRole("complementary", { name: "Workspace navigation" });
  const folder = page.locator(`#case-chats-${caseA.id}`);
  const url = page.url();
  const collapse = nav.getByRole("button", {
    name: `Collapse ${caseA.title}`,
    exact: true,
  });
  await collapse.click();
  await expect(folder).toBeHidden();
  expect(page.url()).toBe(url);
  await page.reload();
  await expect(
    nav.getByRole("button", { name: `Expand ${caseA.title}`, exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await expect(folder).toBeHidden();
  await nav
    .getByRole("button", { name: `Expand ${caseA.title}`, exact: true })
    .focus();
  await page.keyboard.press("Enter");
  await expect(folder).toBeVisible();
  await nav
    .getByRole("button", { name: `Expand ${caseB.title}`, exact: true })
    .click();
  await expect(folder).toBeVisible();
  await expect(page.locator(`#case-chats-${caseB.id}`)).toBeVisible();

  await folder
    .getByRole("button", { name: "Options for New chat", exact: true })
    .click();
  await page
    .getByRole("menuitem", { name: "Archive chat", exact: true })
    .click();
  await expect(
    folder.getByRole("button", { name: "Options for New chat", exact: true }),
  ).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`case=${caseA.id}$`));
  await post({ type: "archive-chat", chatId: personal.id, archived: true });
  await page.reload();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Settings", exact: true });
  await dialog.getByRole("tab", { name: /Archived chats/ }).click();
  const search = dialog.getByRole("searchbox", {
    name: "Search archived chats",
  });
  await search.fill(caseA.title);
  const card = dialog.getByRole("article", { name: "New chat", exact: true });
  await expect(card).toHaveCount(1);
  await expect(card).toContainText(caseA.title);
  await expect(card).toContainText("Archived");
  await page.screenshot({
    path: "test-results/archives-light.png",
    fullPage: true,
  });
  await search.fill("SYNTHETIC no match");
  await expect(
    dialog.getByText("No matching chats", { exact: true }),
  ).toBeVisible();
  await search.fill(caseA.title);
  await card
    .getByRole("button", { name: "Open New chat", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByText("This chat is archived", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Restore chat", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeVisible();
  await expect(
    folder.getByRole("button", { name: "Options for New chat", exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await dialog.getByRole("radio", { name: "Dark", exact: true }).check();
  await dialog.getByRole("tab", { name: /Archived chats/ }).click();
  const personalCard = dialog
    .getByRole("article", { name: "New chat", exact: true })
    .filter({ hasText: "Personal chat" });
  await expect(personalCard).toHaveCount(1);
  await page.screenshot({
    path: "test-results/archives-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/archives-mobile.png",
    fullPage: true,
  });
  await personalCard
    .getByRole("button", { name: "Restore", exact: true })
    .click();
  await expect(personalCard).toHaveCount(0);
  const state: WorkspaceData = await (
    await request.get("/api/workspace")
  ).json();
  expect(
    state.chats.find((item) => item.id === personal.id)?.archivedAt,
  ).toBeUndefined();
  expect(state.chats.find((item) => item.id === chat.id)?.caseId).toBe(
    caseA.id,
  );
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await nav
    .getByRole("button", { name: `Collapse ${caseA.title}`, exact: true })
    .click();
  await expect(folder).toBeHidden();
  await nav
    .getByRole("button", { name: "Options for New chat", exact: true })
    .click();
  await expect(
    page.getByRole("menuitem", { name: "Archive chat", exact: true }),
  ).toBeVisible();
});
