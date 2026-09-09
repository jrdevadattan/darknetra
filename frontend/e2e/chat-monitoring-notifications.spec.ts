import { expect, test } from "@playwright/test";
test("blocked browser permission has clear guidance and never pretends notifications are enabled", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Object.defineProperty(Notification, "permission", { get: () => "denied" });
    Notification.requestPermission = async () => "denied";
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Notifications are blocked",
  );
  await page
    .getByRole("button", { name: "Enable notifications", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Notifications were not allowed",
  );
  await expect(
    page.getByRole("button", { name: "Disable notifications" }),
  ).toHaveCount(0);
});

test("the deployed worker handles a simulated browser push with the workspace page closed", async ({
  page,
  context,
  baseURL,
}) => {
  const origin = new URL(baseURL!).origin;
  await context.grantPermissions(["notifications"], { origin });
  const protocol = await context.newCDPSession(page);
  let registrationId = "";
  protocol.on(
    "ServiceWorker.workerRegistrationUpdated",
    ({ registrations }) => {
      const current = registrations.find(
        (r) => r.scopeURL === origin + "/" && !r.isDeleted,
      );
      if (current) registrationId = current.registrationId;
    },
  );
  await protocol.send("ServiceWorker.enable");
  await page.goto("/");
  const scope = await page.evaluate(async () => {
    await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    return (await navigator.serviceWorker.ready).scope;
  });
  expect(scope).toBe(new URL("/", page.url()).href);
  await expect.poll(() => registrationId).not.toBe("");
  const worker = context.serviceWorkers()[0];
  // This Windows headless browser denies desktop permission even with a grant.
  // Record the real push handler's call at the OS display boundary instead.
  await worker.evaluate(() => {
    const target = globalThis as unknown as {
      registration: ServiceWorkerRegistration;
      syntheticNotices: NotificationOptions[];
    };
    target.syntheticNotices = [];
    target.registration.showNotification = async (_title, options) => {
      target.syntheticNotices.push(options || {});
    };
  });
  await page.goto("about:blank");
  // Chrome's test delivery exercises the real worker without a vendor subscription.
  await protocol.send("ServiceWorker.deliverPushMessage", {
    origin,
    registrationId,
    data: JSON.stringify({
      title: "SYNTHETIC push test",
      body: "SYNTHETIC notification only",
      tag: "SYNTHETIC-worker-test",
      url: "/?chat=SYNTHETIC",
    }),
  });
  await expect
    .poll(() =>
      worker.evaluate(() =>
        (
          globalThis as unknown as { syntheticNotices: NotificationOptions[] }
        ).syntheticNotices.map((n) => n.tag),
      ),
    )
    .toContain("SYNTHETIC-worker-test");
});
test("a chat request starts cron, records notifications with the page closed and exposes pause controls", async ({
  page,
  request,
  baseURL,
}) => {
  test.setTimeout(240_000);
  const origin = new URL(baseURL!).origin;
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(
      "Monitor this SYNTHETIC case every minute. Training fixture only: supplied count is 3. Each check should report the supplied count briefly. Do not use tools, delegate or research any external target. This is a scheduler test, not a real investigation.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("complementary", { name: "Monitoring status" }),
  ).toContainText("every 1 minute");
  await expect(
    page.getByRole("button", { name: "Stop reply", exact: true }),
  ).toHaveCount(0, { timeout: 100_000 });
  const chatId = new URL(page.url()).searchParams.get("chat");
  let data = await (await request.get("/api/workspace")).json();
  const monitor = data.monitors.find(
    (m: { sourceChatId: string }) => m.sourceChatId === chatId,
  );
  expect(monitor).toBeTruthy();
  expect(monitor.enabled).toBe(true);
  expect(monitor.runs[0].trigger).toBe("chat");
  expect(monitor.runs[0].status).toBe("done");
  await page.close();
  await expect
    .poll(
      async () => {
        data = await (await request.get("/api/workspace")).json();
        return data.monitors
          .find((m: { id: string }) => m.id === monitor.id)
          .runs.some(
            (r: { trigger: string; status: string }) =>
              r.trigger === "scheduled" && r.status === "done",
          );
      },
      { timeout: 130_000, intervals: [2000] },
    )
    .toBe(true);
  await request.post("/api/monitors", {
    headers: { origin },
    data: {
      action: "toggle",
      id: monitor.id,
      caseId: monitor.caseId,
      enabled: false,
    },
  });
  const notices = await (await request.get("/api/notifications")).json();
  expect(
    notices.notifications.filter((n: { chatId: string }) => n.chatId === chatId)
      .length,
  ).toBeGreaterThanOrEqual(2);
  expect(notices.privateKey).toBeUndefined();
  expect(notices.devices).toBeUndefined();
  const browserPage = await page.context().newPage();
  await browserPage.goto(`/?case=${monitor.caseId}&chat=${chatId}`);
  await browserPage.getByRole("button", { name: /^Notifications/ }).click();
  await expect(browserPage.getByRole("dialog")).toContainText(
    "Monitoring check complete",
  );
  await browserPage.getByRole("button", { name: "Mark all read" }).click();
  await browserPage.keyboard.press("Escape");
  await browserPage.getByRole("button", { name: "Manage monitoring" }).click();
  await expect(browserPage.getByRole("dialog")).toContainText("Paused");
  await browserPage.keyboard.press("Escape");
  await browserPage
    .getByRole("button", { name: "Settings", exact: true })
    .click();
  await expect(
    browserPage.getByRole("button", {
      name: "Enable notifications",
      exact: true,
    }),
  ).toBeVisible();
  await expect(browserPage.getByRole("dialog")).toContainText(
    "Case details stay inside",
  );
  await browserPage.screenshot({
    path: "test-results/push-settings.png",
    fullPage: true,
    animations: "disabled",
  });
  await browserPage.close();
});
