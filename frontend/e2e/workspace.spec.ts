import { expect, test, type Page } from "@playwright/test";

// Use a local seeded investigator. All persisted records created here are SYNTHETIC.
const username = process.env.DARKNETRA_E2E_USERNAME;
const password = process.env.DARKNETRA_E2E_PASSWORD;
async function login(page: Page) {
  if (!username || !password)
    throw new Error(
      "Set DARKNETRA_E2E_USERNAME and DARKNETRA_E2E_PASSWORD for a local seeded investigator.",
    );
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  const response = page.waitForResponse((r) =>
    r.url().endsWith("/api/v1/auth/login"),
  );
  await page.getByRole("button", { name: "Continue to workspace" }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}
test("private conversation persists, reports unavailable provider, and signs out", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.getByLabel("Model provider").selectOption("OFFLINE");
  const text = `SYNTHETIC UI check ${Date.now()}: explain evidence provenance.`;
  await page.getByRole("textbox", { name: "Message", exact: true }).fill(text);
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page).toHaveURL(/chat=/);
  await expect(
    page.getByRole("alert").filter({ hasText: /UNAVAILABLE|NETWORK_REQUIRED/ }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator(".conversation-content")).toContainText(text);
  await page.getByRole("button", { name: "Conversation settings" }).click();
  await page
    .getByLabel("Title", { exact: true })
    .fill("SYNTHETIC private conversation test");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByRole("heading", { name: "SYNTHETIC private conversation test" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
test("case evidence, retrieval, chat activity, panels, and mobile navigation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  await page.getByRole("button", { name: "Create case", exact: true }).click();
  const title = `SYNTHETIC interface verification ${Date.now()}`;
  await page.getByLabel("Case title").fill(title);
  await page
    .getByLabel("Scope notes")
    .fill("SYNTHETIC test of the local AI Elements workspace.");
  await page.getByLabel("Case type").selectOption("synthetic");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create case" })
    .click();
  await expect(page).toHaveURL(/case=/);
  const caseUrl = page.url();
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Evidence", exact: true }),
  ).toBeVisible();
  await page.locator('.case-content input[type="file"]').setInputFiles({
    name: "SYNTHETIC-research.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "SYNTHETIC training record. The fictional amber notebook is stored in the synthetic archive. No real individuals, vendors, addresses, or identifiers. SYNTHETIC source for retrieval and citation verification.",
    ),
  });
  await page.getByRole("button", { name: "Upload evidence" }).click();
  await expect(page.getByText("1 accepted; 0 rejected.")).toBeVisible();
  await page
    .locator(".data-table button")
    .filter({ hasText: "SYNTHETIC-research.txt" })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "SYNTHETIC-research.txt",
  );
  await page.getByRole("button", { name: "Verify hash" }).click();
  await expect(page.getByText("Integrity check recorded")).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page
    .getByRole("button", { name: "Search & retrieval", exact: true })
    .click();
  await page.getByLabel("Query", { exact: true }).fill("amber notebook");
  await page.getByLabel("Retrieval mode").selectOption("lexical");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.locator(".case-content")).toContainText("amber notebook");
  await page.goto(caseUrl);
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill("amber notebook");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page).toHaveURL(/thread=/);
  await expect(
    page.locator(".message-author").filter({ hasText: "Darknetra" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Used 1 sources" }).click();
  await expect(
    page.getByText("Verified citation", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".conversation-content .evidence-chip"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Toggle agent activity" }).click();
  await expect(
    page.getByRole("complementary", { name: "Agent activity" }),
  ).toBeVisible();
  await expect(page.locator(".graph-node").first()).toBeVisible();
  await expect(
    page.getByText("Run in progress. Waiting for a verified response…", {
      exact: true,
    }),
  ).toHaveCount(0);
  await page.screenshot({
    path: "test-results/case-graph-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("tab", { name: "Output", exact: true }).click();
  await expect(page.getByText("Run log", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/case-chat-desktop.png",
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.locator(".message-author").filter({ hasText: "Darknetra" }),
  ).toBeVisible();
  for (const [button, heading] of [
    ["Overview", "Case overview"],
    ["Entities", "Entities"],
    ["Relationships", "Relationships"],
    ["Findings", "Findings & decisions"],
    ["Monitoring", "Monitoring"],
    ["Alerts", "Alerts"],
    ["Reports", "Investigation packs"],
    ["Sharing & policy", "Members & policy"],
    ["Audit trail", "Case audit"],
  ]) {
    await page.getByRole("button", { name: button, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".error-banner")).toHaveCount(0);
  }
  await page
    .getByRole("button", { name: "Tools & integrations", exact: true })
    .click();
  await expect(page.locator(".plugin-card").first()).toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Service health" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Light", exact: true }).click();
  await expect(page.locator("html")).toHaveClass(/light/);
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Message", exact: true }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator(".sidebar")
        .evaluate((el) => el.getBoundingClientRect().right),
    )
    .toBeLessThanOrEqual(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/private-chat-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(errors).toEqual([]);
});

test("expired access refreshes for sign-out and lost sessions return to login", async ({
  page,
  context,
}) => {
  await login(page);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Service health" }),
  ).toBeVisible();
  await context.clearCookies({ name: "darknetra_access" });
  await page.route("**/api/v1/auth/refresh", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "NETWORK_REQUIRED",
          message: "SYNTHETIC temporary refresh outage",
        },
      }),
    }),
  );
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.locator(".error-banner")).toContainText(
    "SYNTHETIC temporary refresh outage",
  );
  await expect(page.locator(".sidebar")).toBeVisible();
  await page.unroute("**/api/v1/auth/refresh");
  const refreshed = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/auth/refresh") &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "Sign out" }).click();
  await refreshed;
  await expect(page.getByLabel("Username", { exact: true })).toBeVisible();

  await login(page);
  await context.clearCookies();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
  await expect(page.locator(".sidebar")).toHaveCount(0);
});
