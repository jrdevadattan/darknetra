import { expect, test } from "@playwright/test";

test("settings switch and persist themes, follow the device, and work on mobile", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Settings", exact: true });
  await dialog.getByRole("radio", { name: "Light", exact: true }).check();
  await expect(page.locator("html")).toHaveClass("light");
  expect(
    await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
  ).toBe("rgb(246, 248, 243)");
  await page.screenshot({
    path: "test-results/settings-light.png",
    fullPage: true,
  });
  await page.reload();
  await expect(page.locator("html")).toHaveClass("light");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    dialog.getByRole("radio", { name: "Light", exact: true }),
  ).toBeChecked();
  await dialog.getByRole("radio", { name: "Dark", exact: true }).check();
  await expect(page.locator("html")).toHaveClass("dark");
  await page.screenshot({
    path: "test-results/settings-dark.png",
    fullPage: true,
  });
  await dialog.getByRole("radio", { name: "System", exact: true }).check();
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveClass("light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveClass("dark");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Settings", exact: true }),
  ).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(dialog).toBeInViewport();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
