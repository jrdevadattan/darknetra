import { expect, test, type Locator, type Page } from "@playwright/test";
import type { WorkspaceData, RunSource } from "../lib/chat-types";

const at = "2026-09-08T10:00:00Z";
const sources: RunSource[] = Array.from({ length: 4 }, (_, i) => ({
  id: `url:https://example.com/SYNTHETIC-${i}`,
  url: `https://example.com/SYNTHETIC-${i}`,
  title: `SYNTHETIC bulletin ${i + 1}`,
  kind: "page",
  status: i === 3 ? "listed" : "retrieved",
  excerpt: "SYNTHETIC source used only for interface verification.",
}));
const fixture: WorkspaceData = {
  version: 1,
  cases: [],
  chats: [
    {
      id: "SYNTHETIC-layout",
      caseId: null,
      title: "SYNTHETIC long investigation",
      createdAt: at,
      messages: [
        {
          id: "SYNTHETIC-reply",
          role: "assistant",
          at,
          status: "done",
          text: "SYNTHETIC review complete. Forty checks were unsuccessful; they do not establish that the sources are offline. [Public bulletin](https://example.com/SYNTHETIC-0)",
          activity: [
            ...Array.from({ length: 40 }, (_, i) => ({
              id: `SYNTHETIC-check-${i}`,
              label: "Reading a source",
              status: "failed",
              at,
              targetUrl: `https://example.org/SYNTHETIC-${i}`,
              result: `SYNTHETIC check ${i + 1} could not be completed.`,
            })),
            {
              id: "SYNTHETIC-source-read",
              label: "Reading a source",
              status: "completed",
              at,
              sources,
            },
          ],
          agents: [
            {
              id: "SYNTHETIC-analyst",
              name: "Research Analyst",
              role: "research_analyst",
              task: "SYNTHETIC reference review.",
              status: "completed",
              result: "SYNTHETIC report returned.",
              activity: [],
            },
          ],
        },
      ],
    },
  ],
};
async function drag(page: Page, handle: Locator, delta: number) {
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + delta, box.y + box.height / 2, {
    steps: 12,
  });
  await page.mouse.up();
}
async function width(panel: Locator) {
  return Math.round((await panel.boundingBox())!.width);
}

test("panels resize on either side and retain widths; long graphs open as a readable overview", async ({
  page,
  context,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await context.route("**/api/workspace", (route) =>
    route.fulfill({ json: fixture }),
  );
  await page.addInitScript(() => {
    if (!localStorage.getItem("theme")) localStorage.setItem("theme", "light");
  });
  await page.goto("/?chat=SYNTHETIC-layout");
  await page.getByRole("button", { name: /View run/ }).click();
  const nav = page.getByRole("complementary", { name: "Workspace navigation" });
  const panel = page.getByRole("complementary", { name: "Agent activity" });
  const navHandle = page.getByRole("separator", {
    name: "Resize navigation sidebar",
  });
  const activityHandle = page.getByRole("separator", {
    name: "Resize activity sidebar",
  });
  await expect(
    panel.getByRole("button", { name: "Overview", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(panel.locator(".react-flow__node")).toHaveCount(8);
  await expect(panel.locator(".evidence-canvas")).toContainText(
    "40 unsuccessful checks",
  );
  expect(
    parseInt(await panel.getByLabel("Graph zoom").innerText()),
  ).toBeGreaterThanOrEqual(65);
  await drag(page, navHandle, -60);
  expect(await width(nav)).toBe(190);
  await drag(page, activityHandle, -120);
  expect(await width(panel)).toBe(400);
  await page
    .getByRole("button", { name: "Swap conversation and activity" })
    .click();
  await drag(page, activityHandle, 70);
  expect(await width(panel)).toBe(330);
  await page.reload();
  await page.getByRole("button", { name: /View run/ }).click();
  expect(await width(nav)).toBe(190);
  expect(await width(panel)).toBe(330);
  await activityHandle.focus();
  await page.keyboard.press("ArrowLeft");
  expect(await width(panel)).toBe(346);
  await activityHandle.dblclick();
  expect(await width(panel)).toBe(520);
  await navHandle.focus();
  await page.keyboard.press("Home");
  expect(await width(nav)).toBe(180);
  await panel.getByRole("textbox", { name: "Search graph" }).fill("bulletin 4");
  await panel.locator(".graph-search-results button").click();
  await expect(
    panel.getByRole("article", { name: "Selected graph item" }),
  ).toContainText("Unverified reference");
  await expect(panel.getByLabel("Graph zoom")).toHaveText("100%");
  await panel
    .getByRole("textbox", { name: "Search graph" })
    .fill("unsuccessful");
  await panel.locator(".graph-search-results button").click();
  await expect(
    panel.getByRole("article", { name: "Selected graph item" }),
  ).toContainText("SYNTHETIC check 40");
  await panel.getByRole("button", { name: "View all 40 checks" }).click();
  await expect(
    panel.getByRole("button", { name: "All steps", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(panel.locator(".react-flow__node")).toHaveCount(48);
  await panel.getByRole("button", { name: "Overview", exact: true }).click();
  await panel.getByRole("button", { name: "Fit entire graph" }).click();
  await panel
    .getByRole("button", { name: "Expand activity", exact: true })
    .click();
  await expect(activityHandle).toHaveCount(0);
  await expect(panel.locator(".react-flow__node").filter({ hasText: "SYNTHETIC bulletin 1" })).toBeInViewport();
  await expect.poll(async () => parseInt(await panel.getByLabel("Graph zoom").innerText())).toBeGreaterThanOrEqual(65);
  await page.screenshot({
    path: "test-results/graph-overview-light.png",
    fullPage: true,
  });
  await panel
    .getByRole("button", { name: "Collapse activity", exact: true })
    .click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("radio", { name: "Dark", exact: true }).check();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /View run/ }).click();
  await expect(panel.locator(".react-flow__node").filter({ hasText: "SYNTHETIC bulletin 1" })).toBeInViewport();
  await page.screenshot({
    path: "test-results/resizable-panels-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(nav).not.toBeInViewport();
  await expect(
    page.getByRole("separator", { name: "Resize activity sidebar" }),
  ).toHaveCount(0);
  await expect(panel).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/graph-overview-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
