import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
import type { WorkspaceData, RunSource } from "../lib/chat-types";

const at = "2026-09-08T10:00:00Z";
const favicon =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=";
const source: RunSource = {
  id: "url:https://example.com/",
  url: "https://example.com/",
  title: "SYNTHETIC public bulletin",
  kind: "page",
  status: "retrieved",
  excerpt: "SYNTHETIC reference retrieved for this review.",
  at,
  favicon,
};
const file = {
  name: "SYNTHETIC-notes.txt",
  label: "SYNTHETIC case notes.txt",
  size: 42,
};
const data: WorkspaceData = {
  version: 1,
  cases: [
    {
      id: "SYNTHETIC-case",
      title: "SYNTHETIC source review",
      notes: "Interface verification",
      createdAt: at,
    },
  ],
  chats: [
    {
      id: "SYNTHETIC-chat",
      caseId: "SYNTHETIC-case",
      title: "SYNTHETIC bulletin review",
      createdAt: at,
      messages: [
        {
          id: "SYNTHETIC-input",
          role: "user",
          text: "SYNTHETIC review https://example.com/ using the attached notes.",
          status: "done",
          at,
          activity: [],
          attachments: [file],
        },
        {
          id: "SYNTHETIC-reply",
          role: "assistant",
          text: "The [public bulletin](https://example.com/) has been reviewed alongside the [case notes](SYNTHETIC-notes.txt). This is a SYNTHETIC interface demonstration.",
          status: "done",
          at,
          finishedAt: at,
          activity: [
            {
              id: "SYNTHETIC-read",
              label: "Reading a source",
              kind: "action",
              status: "completed",
              at,
              finishedAt: at,
              sources: [source],
              result: "One public source reviewed.",
            },
          ],
          agents: [
            {
              id: "SYNTHETIC-research",
              name: "Research Analyst",
              role: "research_analyst",
              status: "completed",
              task: "Review the SYNTHETIC public reference and report its provenance.",
              result:
                "Reviewed the [public bulletin](https://example.com/). The source is ready for the lead investigator.",
              activity: [
                {
                  id: "SYNTHETIC-review",
                  label: "Reviewing information",
                  status: "completed",
                  detail:
                    "Compared the supplied notes with the public reference.",
                  at,
                },
              ],
            },
          ],
        },
      ],
    },
  ],
};

test("sources, specialist reports and graph connections are interactive with local favicon assets", async ({
  page,
  context,
  request,
  baseURL,
}) => {
  const origin = new URL(baseURL!).origin;
  const created = await request.post("/api/workspace", {
    headers: { origin },
    data: { type: "chat", caseId: null },
  });
  expect(created.ok()).toBe(true);
  const chatId = (await created.json()).id;
  const upload = await request.post(`/api/chat/${chatId}/files`, {
    headers: { origin },
    multipart: {
      file: {
        name: file.name,
        mimeType: "text/plain",
        buffer: Buffer.from("SYNTHETIC attached notes"),
      },
    },
  });
  expect(upload.ok()).toBe(true);
  const uploaded = await upload.json();
  const fixture = JSON.parse(
    JSON.stringify(data)
      .replaceAll("SYNTHETIC-chat", chatId)
      .replaceAll(file.name, uploaded.name)
      .replaceAll(file.label, uploaded.label),
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await context.route("**/api/workspace", (route) =>
    route.fulfill({ json: fixture }),
  );
  await context.route("https://example.com/", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<title>SYNTHETIC linked website</title>",
    }),
  );
  await page.addInitScript(() => localStorage.setItem("theme", "light"));
  await page.goto(`/?case=SYNTHETIC-case&chat=${chatId}`);
  const conversation = page.getByRole("region", {
    name: "Conversation",
    exact: true,
  });
  await expect(conversation.locator(".plain-source-link")).toHaveAttribute(
    "href",
    source.url!,
  );
  const citation = conversation.getByRole("link", {
    name: "public bulletin",
    exact: true,
  });
  await expect(citation).toBeVisible();
  await expect(citation.locator("img")).toHaveAttribute("src", favicon);
  expect(
    await citation
      .locator("img")
      .evaluate(
        (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
      ),
  ).toBe(true);
  await expect(
    conversation.getByRole("link", { name: "case notes", exact: true }),
  ).toHaveAttribute("href", `/api/chat/${chatId}/files?name=${uploaded.name}`);
  await page.getByRole("button", { name: /View run/ }).click();
  const panel = page.getByRole("complementary", { name: "Agent activity" });
  await panel.getByRole("tab", { name: "Timeline", exact: true }).click();
  const step = panel.locator('[data-activity-id="SYNTHETIC-read"]');
  await expect(step.locator(".timeline-marker img")).toBeVisible();
  await step.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(step.locator(".source-tile")).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(step.locator(".source-tile")).toBeHidden();
  await page.keyboard.press("Enter");
  await expect(step.locator(".source-tile")).toBeVisible();
  const specialist = panel.locator(".specialist-card");
  await specialist.getByRole("button", { name: /Research Analyst/ }).click();
  await expect(specialist.locator(".specialist-body")).toHaveCount(0);
  await specialist.getByRole("button", { name: /Research Analyst/ }).click();
  await specialist.getByText("View specialist report").click();
  await expect(specialist.locator(".agent-result a")).toHaveAttribute(
    "href",
    source.url!,
  );
  await page.screenshot({
    path: "test-results/sources-light.png",
    fullPage: true,
  });
  await step.getByRole("button", { name: /SYNTHETIC public bulletin/ }).click();
  await expect(
    panel.getByRole("tab", { name: "Evidence graph" }),
  ).toHaveAttribute("aria-selected", "true");
  const inspector = panel.getByRole("article", { name: "Selected graph item" });
  await expect(inspector).toContainText(source.excerpt!);
  await expect(inspector.locator(".site-icon img")).toBeVisible();
  await expect(
    inspector.getByRole("button", { name: "Copy link", exact: true }),
  ).toBeVisible();
  await panel
    .locator(".source-directory > summary")
    .filter({ hasText: "sources" })
    .click();
  const popupPromise = page.waitForEvent("popup");
  await panel
    .getByRole("link", { name: `Open website: ${source.title}`, exact: true })
    .click();
  const popup = await popupPromise;
  await expect(popup).toHaveTitle("SYNTHETIC linked website");
  await popup.close();
  const downloadPromise = page.waitForEvent("download");
  await panel
    .getByRole("link", {
      name: `Download file: ${uploaded.label}`,
      exact: true,
    })
    .click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(uploaded.label);
  expect(await readFile((await download.path())!, "utf8")).toBe(
    "SYNTHETIC attached notes",
  );
  // Keyboard selection works for graph nodes, then an edge opens its relationship.
  const report = panel
    .locator(".react-flow__node")
    .filter({ hasText: "Investigation report" });
  await report.focus();
  await page.keyboard.press("Enter");
  await expect(inspector).toContainText("Investigation report");
  await panel
    .locator(".react-flow__edge-textwrapper")
    .filter({ hasText: /^supplied$/ })
    .first()
    .click();
  await expect(
    panel.getByRole("article", { name: "Selected connection" }),
  ).toBeVisible();
  await panel.locator(".connection-links button").first().click();
  await expect(inspector).toBeVisible();
  await panel.locator(".connection-directory > summary").click();
  await panel
    .locator(".connection-directory button")
    .filter({ hasText: "assigned" })
    .click();
  await expect(
    panel.getByRole("article", { name: "Selected connection" }),
  ).toContainText("assigned");
  await page.getByRole("tab", { name: "Timeline", exact: true }).click();
  await page
    .getByRole("button", { name: "View lead investigator report" })
    .click();
  await expect(
    panel.getByRole("tab", { name: "Output", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(panel.locator(".output-report a").first()).toHaveAttribute(
    "href",
    source.url!,
  );
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("radio", { name: "Dark", exact: true }).check();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /View run/ }).click();
  await panel.getByRole("tab", { name: "Timeline", exact: true }).click();
  await page.screenshot({
    path: "test-results/sources-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("complementary", { name: "Workspace navigation" }),
  ).not.toBeInViewport();
  await expect(panel).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(await panel.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: "test-results/sources-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
