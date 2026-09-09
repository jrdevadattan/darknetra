import { afterEach, expect, test, vi } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
vi.mock("./push", () => ({
  deliverPush: vi.fn(async () => ({ sent: 0, failed: 0 })),
}));
vi.mock("./codex", () => ({
  isChatRunning: vi.fn(() => false),
  startRun: vi.fn(async () => ({
    message: { id: "SYNTHETIC-reply" },
    completion: Promise.resolve({
      id: "SYNTHETIC-reply",
      status: "done",
      text: "SYNTHETIC result",
    }),
  })),
}));
import { startRun } from "./codex";
import { createCase, loadWorkspace } from "./store";
import { createMonitor } from "./monitors";
import { ensureMonitorScheduler } from "./monitor-scheduler";
let directory: string;
afterEach(async () => {
  const shared = globalThis as typeof globalThis & {
    caseMonitorScheduler?: { clock?: ReturnType<typeof setInterval> };
  };
  clearInterval(shared.caseMonitorScheduler?.clock);
  delete shared.caseMonitorScheduler;
  vi.useRealTimers();
  vi.unstubAllEnvs();
  if (directory) await rm(directory, { recursive: true, force: true });
});
test("a tick before the cron deadline does not lose the run when the next tick is late", async () => {
  directory = await mkdtemp(path.join(tmpdir(), "SYNTHETIC-cron-clock-"));
  vi.stubEnv("CODEX_CHAT_DATA_DIR", directory);
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
  vi.setSystemTime(new Date("2026-09-08T09:00:01Z"));
  const c = await createCase("SYNTHETIC clock", "");
  await createMonitor({
    caseId: c.id,
    title: "SYNTHETIC clock",
    prompt: "SYNTHETIC",
    cron: "* * * * *",
    timezone: "UTC",
  });
  await ensureMonitorScheduler();
  await vi.advanceTimersByTimeAsync(55000); // Last tick before the 09:01 deadline.
  expect(startRun).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(5000); // 09:01:01, already past the exact boundary.
  await vi.waitFor(() => expect(startRun).toHaveBeenCalledTimes(1));
  await vi.waitFor(async () =>
    expect((await loadWorkspace()).monitors![0].runs[0].status).toBe("done"),
  );
  await vi.advanceTimersByTimeAsync(10000);
  expect(startRun).toHaveBeenCalledTimes(1);
});
