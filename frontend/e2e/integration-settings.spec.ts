import { expect, test } from "@playwright/test";

test("intelligence settings shows actual CLI credential state and works on mobile", async ({
  page,
  request,
}) => {
  const response = await request.get("/api/integrations");
  expect(response.ok()).toBe(true);
  const data = await response.json();
  expect(data.providers.map((p: { id: string }) => p.id)).toEqual([
    "flashpoint",
    "recorded-future",
    "chainalysis",
    "apify",
  ]);
  expect(
    data.providers.every(
      (p: { state: string }) => p.state === "credentials_required",
    ),
  ).toBe(true);
  expect(JSON.stringify(data)).not.toContain("SYNTHETIC-private");
  await page.addInitScript(() => localStorage.setItem("theme", "light"));
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const integrations = page.getByRole("region", {
    name: "Intelligence integrations",
  });
  await expect(
    integrations.getByText("API key required", { exact: true }),
  ).toHaveCount(4);
  await expect(
    integrations.getByRole("link", { name: "Open Flashpoint setup" }),
  ).toHaveAttribute("href", "https://app.flashpoint.io/");
  await integrations
    .getByText("Connect your accounts", { exact: true })
    .click();
  await expect(integrations).toContainText(
    "frontend/.codex-chat/providers.json",
  );
  await expect(integrations).toContainText(
    "Reactor tracing and KYT monitoring require their separate customer integrations",
  );
  await integrations
    .getByRole("button", { name: "Refresh integration status" })
    .click();
  await expect(
    integrations.getByRole("button", { name: "Refresh integration status" }),
  ).toBeEnabled();
  await integrations.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/integrations-light.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await integrations
    .getByText("Chainalysis Sanctions", { exact: true })
    .scrollIntoViewIfNeeded();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const dialog = page.getByRole("dialog");
  expect(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/integrations-mobile.png",
    fullPage: true,
  });
});
