import { expect, test } from "@playwright/test";
test("clock and day choices save the correct schedule without typing cron", async ({
  page,
  request,
  baseURL,
}) => {
  const origin = new URL(baseURL!).origin;
  const response = await request.post("/api/workspace", {
    headers: { origin },
    data: { type: "case", title: "SYNTHETIC clock picker" },
  });
  const caseData = await response.json();
  await page.goto(`/?case=${caseData.id}`);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("radio", { name: "Light", exact: true }).check();
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Case monitoring", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  const repeat = dialog.getByRole("combobox", { name: "Repeat", exact: true });
  await expect(repeat.locator("option")).toHaveText([
    "Interval",
    "Daily",
    "Weekdays",
    "Weekly",
    "Custom",
  ]);
  await dialog.getByLabel("Schedule name").fill("SYNTHETIC weekday check");
  await dialog
    .getByLabel("What should be checked?")
    .fill("SYNTHETIC fixture only. No external tools or research.");
  await expect(dialog.getByLabel("Cron expression")).toHaveCount(0);
  await dialog.getByLabel("Time of day").fill("00:05");
  await expect(dialog.getByRole("status")).toContainText(
    "Every day at 12:05 AM",
  );
  await dialog
    .getByRole("combobox", { name: "Repeat", exact: true })
    .selectOption("interval");
  await dialog.getByRole("combobox", { name: "Check every" }).selectOption("5");
  await expect(dialog.getByRole("status")).toContainText("Every 5 minutes");
  await dialog
    .getByRole("combobox", { name: "Interval unit", exact: true })
    .selectOption("hours");
  await dialog
    .getByRole("combobox", { name: "Check every", exact: true })
    .selectOption("2");
  await expect(dialog.getByRole("status")).toContainText("Every 2 hours");
  await expect(dialog.getByLabel("Time of day")).toHaveCount(0);
  await repeat.selectOption({ label: "Weekdays" });
  await dialog.getByLabel("Time of day").fill("08:30");
  await expect(dialog.getByRole("status")).toContainText("Weekdays at 8:30 AM");
  await repeat.selectOption({ label: "Weekly" });
  await dialog.getByLabel("Day of the week").selectOption("0");
  await dialog.getByLabel("Time of day").fill("17:20");
  await expect(dialog.getByRole("status")).toContainText(
    "Every Sunday at 5:20 PM",
  );
  await dialog
    .getByRole("combobox", { name: "Repeat", exact: true })
    .selectOption("custom");
  await expect(repeat).toBeVisible();
  await expect(dialog.locator(".custom-clock")).toBeVisible();
  await expect(
    dialog.getByText("Choose the time of day and when to repeat."),
  ).toBeVisible();
  await dialog.getByLabel("Time of day").fill("23:45");
  await dialog
    .getByRole("combobox", { name: "Timezone", exact: true })
    .selectOption("UTC");
  for (const day of [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
  ])
    await dialog.getByRole("button", { name: day, exact: true }).click();
  await expect(
    dialog.getByRole("button", { name: "Save schedule" }),
  ).toBeDisabled();
  for (const day of ["Monday", "Wednesday", "Friday"])
    await dialog.getByRole("button", { name: day, exact: true }).click();
  await expect(dialog.getByRole("status")).toContainText(
    "Mon, Wed, Fri at 11:45 PM",
  );
  await expect(
    dialog.getByRole("button", { name: "Choose time", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/schedule-clock.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expect(
    dialog.getByRole("button", { name: "Friday", exact: true }),
  ).toBeVisible();
  await expect(repeat).toBeVisible();
  await page.screenshot({
    path: "test-results/schedule-frequency-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  await dialog.getByRole("button", { name: "Save schedule" }).click();
  await expect(
    dialog.getByText("SYNTHETIC weekday check", { exact: true }),
  ).toBeVisible();
  const data = await (
    await request.get(`/api/monitors?caseId=${caseData.id}`)
  ).json();
  expect(data.monitors[0].cron).toBe("45 23 * * 1,3,5");
  expect(data.monitors[0].timezone).toBe("UTC");
  await request.post("/api/monitors", {
    headers: { origin },
    data: {
      action: "toggle",
      id: data.monitors[0].id,
      caseId: caseData.id,
      enabled: false,
    },
  });
  await page.reload();
  await page
    .getByRole("button", { name: "Case monitoring", exact: true })
    .click();
  await expect(dialog).toContainText("Mon, Wed, Fri at 11:45 PM");
});
