import { expect, test } from "@playwright/test";
import type { WorkspaceData } from "../lib/chat-types";

const at = "2026-09-08T10:00:00Z";
const favicon =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=";
const fixture: WorkspaceData = {
  version: 1,
  cases: [],
  chats: [
    {
      id: "SYNTHETIC-activity",
      title: "SYNTHETIC public reference review",
      caseId: null,
      createdAt: at,
      messages: [
        {
          id: "SYNTHETIC-run",
          role: "assistant",
          status: "running",
          at,
          text: "SYNTHETIC review in progress.",
          activity: [
            {
              id: "SYNTHETIC-update",
              label: "Progress update",
              kind: "update",
              status: "completed",
              at,
              detail:
                "I am checking the supplied references and comparing the published archive. The research analyst is reviewing the source history.",
            },
            {
              id: "SYNTHETIC-legacy",
              label: "Checking case material",
              status: "completed",
              at,
              finishedAt: "2026-09-08T10:00:04Z",
              detail: `/bin/bash -lc "node .agents/skills/darknetra-osint/scripts/osint.mjs page 'https://example.com/SYNTHETIC/reference'"`,
            },
            {
              id: "SYNTHETIC-running",
              label: "Checking archive history",
              status: "running",
              at,
              targetUrl: "https://example.org/SYNTHETIC/archive",
            },
            {
              id: "SYNTHETIC-unavailable",
              label: "Checking public indexes",
              status: "completed",
              at,
              targetUrl: "https://example.net/SYNTHETIC/index",
              result:
                "This check could not be completed (NETWORK_REQUIRED). This does not establish that there are no matches.",
            },
          ],
          agents: [
            {
              id: "SYNTHETIC-analyst",
              name: "Research Analyst",
              role: "research_analyst",
              status: "completed",
              task: "Compare the SYNTHETIC bulletin with the published archive.",
              result: "SYNTHETIC reference review completed.",
              activity: [
                {
                  id: "SYNTHETIC-source",
                  label: "Reading a source",
                  status: "completed",
                  at,
                  sources: [
                    {
                      id: "url:https://example.org/SYNTHETIC/bulletin",
                      title: "SYNTHETIC public bulletin",
                      kind: "page",
                      status: "retrieved",
                      url: "https://example.org/SYNTHETIC/bulletin",
                      excerpt: "SYNTHETIC bulletin saved for review.",
                      favicon,
                    },
                  ],
                },
                {
                  id: "SYNTHETIC-history",
                  label: "Checking archive history",
                  status: "completed",
                  at,
                  targetUrl: "https://example.org/SYNTHETIC/history",
                },
              ],
            },
          ],
        },
      ],
    },
  ],
};

test("activity cards keep commands tucked away and filter lead and specialist steps", async ({
  page,
  context,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await context.route("**/api/workspace", (route) =>
    route.fulfill({ json: fixture }),
  );
  await page.addInitScript(() => localStorage.setItem("theme", "light"));
  await page.goto("/?chat=SYNTHETIC-activity");
  const panel = page.getByRole("complementary", { name: "Agent activity" });
  if (!(await panel.isVisible()))
    await page.getByRole("button", { name: /View run/ }).click();
  await panel.getByRole("tab", { name: "Timeline", exact: true }).click();
  await expect(panel.locator("[data-activity-id]")).toHaveCount(6);
  const legacy = panel.locator('[data-activity-id="SYNTHETIC-legacy"]');
  await expect(legacy.locator(".timeline-heading")).toContainText(
    "Reading a source",
  );
  await expect(legacy.locator(".timeline-preview")).toHaveText("example.com");
  await expect(legacy.locator(".timeline-heading")).not.toContainText(
    "/bin/bash",
  );
  await legacy.locator(".timeline-heading").focus();
  await page.keyboard.press("Enter");
  await expect(legacy.locator(".active-website")).toHaveAttribute(
    "href",
    "https://example.com/SYNTHETIC/reference",
  );
  await expect(legacy.locator("pre")).toBeHidden();
  await legacy.getByText("Technical details", { exact: true }).click();
  await expect(legacy.locator("pre")).toContainText("/bin/bash");
  await legacy.locator(".timeline-heading").click();
  await panel.getByRole("button", { name: /Needs attention/ }).click();
  await expect(panel.locator("[data-activity-id]")).toHaveCount(1);
  const unsuccessful = panel.locator(
    '[data-activity-id="SYNTHETIC-unavailable"]',
  );
  await expect(unsuccessful.locator(".step-status")).toHaveText(
    "Needs attention",
  );
  await unsuccessful.locator(".timeline-heading").click();
  await expect(unsuccessful).toContainText(
    "does not establish that there are no matches",
  );
  await panel.getByRole("button", { name: /Working/ }).click();
  await expect(panel.locator("[data-activity-id]")).toHaveCount(1);
  await expect(
    panel.locator('[data-activity-id="SYNTHETIC-running"]'),
  ).toBeVisible();
  await panel.getByRole("button", { name: /All activity/ }).click();
  await panel
    .getByRole("textbox", { name: "Search activity" })
    .fill("research analyst");
  await expect(panel.locator("[data-activity-id]")).toHaveCount(3);
  await panel
    .getByRole("textbox", { name: "Search activity" })
    .fill("bulletin");
  await expect(panel.locator("[data-activity-id]")).toHaveCount(1);
  const source = panel.locator('[data-activity-id="SYNTHETIC-source"]');
  await expect(source.locator(".timeline-marker img")).toHaveAttribute(
    "src",
    favicon,
  );
  await source.locator(".timeline-heading").click();
  await expect(source.locator(".source-tile")).toBeVisible();
  await panel
    .getByRole("textbox", { name: "Search activity" })
    .fill("no matching SYNTHETIC reference");
  await expect(panel.getByText("No matching activity")).toBeVisible();
  await panel.getByRole("button", { name: "Show all activity" }).click();
  await expect(panel.locator("[data-activity-id]")).toHaveCount(6);
  await panel
    .getByRole("button", { name: "Expand activity", exact: true })
    .click();
  await page.screenshot({
    path: "test-results/activity-timeline-light.png",
    fullPage: true,
  });
  await panel
    .getByRole("button", { name: "Collapse activity", exact: true })
    .click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("radio", { name: "Dark", exact: true }).check();
  await page.keyboard.press("Escape");
  if (!(await panel.isVisible()))
    await page.getByRole("button", { name: /View run/ }).click();
  await panel.getByRole("tab", { name: "Timeline", exact: true }).click();
  await page.screenshot({
    path: "test-results/activity-timeline-dark.png",
    fullPage: true,
  });
  const resize = page.getByRole("separator", {
    name: "Resize activity sidebar",
  });
  await resize.focus();
  await page.keyboard.press("Home");
  expect(
    await panel
      .locator(".activity-view")
      .evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
  await panel
    .locator('[data-activity-id="SYNTHETIC-source"] .timeline-heading')
    .click();
  await panel
    .locator('[data-activity-id="SYNTHETIC-source"] .source-tile')
    .scrollIntoViewIfNeeded();
  expect(
    await panel
      .locator(".activity-view")
      .evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
  await panel.locator(".activity-view").evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(panel).toBeInViewport();
  expect(await panel.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
  expect(
    await panel
      .locator(".activity-view")
      .evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/activity-timeline-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
