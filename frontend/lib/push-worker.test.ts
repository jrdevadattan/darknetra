import { expect, test, vi } from "vitest";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
test("the worker displays pushed updates and restricts notification clicks to this workspace", async () => {
  const handlers: Record<string, (event: unknown) => void> = {};
  const showNotification = vi.fn(async () => {}),
    openWindow = vi.fn(async () => {});
  const self = {
    location: { origin: "http://127.0.0.1:3100" },
    addEventListener: (name: string, handler: (event: unknown) => void) => {
      handlers[name] = handler;
    },
    registration: { showNotification },
    clients: { matchAll: async () => [], openWindow },
  };
  runInNewContext(await readFile("public/sw.js", "utf8"), { self, URL });
  let pending: Promise<unknown> = Promise.resolve();
  handlers.push({
    data: {
      json: () => ({
        title: "SYNTHETIC update",
        body: "SYNTHETIC result",
        url: "/?case=SYNTHETIC&chat=SYNTHETIC",
      }),
    },
    waitUntil: (p: Promise<unknown>) => {
      pending = p;
    },
  });
  await pending;
  expect(showNotification.mock.calls[0]).toMatchObject([
    "SYNTHETIC update",
    { data: { url: "/?case=SYNTHETIC&chat=SYNTHETIC" } },
  ]);
  const close = vi.fn();
  handlers.notificationclick({
    notification: { data: { url: "https://example.invalid/" }, close },
    waitUntil: (p: Promise<unknown>) => {
      pending = p;
    },
  });
  await pending;
  expect(openWindow).not.toHaveBeenCalled();
  handlers.notificationclick({
    notification: { data: { url: "/?case=SYNTHETIC&chat=SYNTHETIC" }, close },
    waitUntil: (p: Promise<unknown>) => {
      pending = p;
    },
  });
  await pending;
  expect(openWindow).toHaveBeenCalledWith(
    "http://127.0.0.1:3100/?case=SYNTHETIC&chat=SYNTHETIC",
  );
});
