import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
vi.mock("./push", () => ({
  deliverPush: vi.fn(async () => ({ sent: 0, failed: 0 })),
}));
import { deliverPush } from "./push";
import { createCase, loadWorkspace, mutateWorkspace } from "./store";
import {
  createMonitor,
  claimMonitor,
  finishMonitor,
  nextOccurrence,
  recoverMonitors,
  setMonitorEnabled,
} from "./monitors";
let directory: string;
beforeEach(async () => {
  directory = await mkdtemp(path.join(tmpdir(), "SYNTHETIC-monitors-"));
  vi.stubEnv("CODEX_CHAT_DATA_DIR", directory);
});
afterEach(async () => {
  vi.unstubAllEnvs();
  await rm(directory, { recursive: true, force: true });
});
test("five-field cron uses the chosen timezone and rejects malformed or impossible schedules", () => {
  expect(
    nextOccurrence(
      "0 9 * * *",
      "Asia/Kolkata",
      new Date("2026-09-08T01:00:00Z"),
    ),
  ).toBe("2026-09-08T03:30:00.000Z");
  expect(() => nextOccurrence("* * * * * *", "UTC")).toThrow();
  expect(() => nextOccurrence("0 0 31 2 *", "UTC")).toThrow();
  expect(() => nextOccurrence("* * * * *", "invalid")).toThrow();
});
test("claims are atomic, pause blocks scheduled work, history and case scope survive reload", async () => {
  const a = await createCase("SYNTHETIC A", "");
  const b = await createCase("SYNTHETIC B", "");
  const monitor = await createMonitor({
    caseId: a.id,
    title: "SYNTHETIC watch",
    prompt: "SYNTHETIC check",
    cron: "* * * * *",
    timezone: "UTC",
  });
  await mutateWorkspace((data) => {
    data.monitors![0].nextRunAt = "2020-01-01T00:00:00Z";
  });
  const claims = await Promise.all([
    claimMonitor(monitor.id, a.id, "scheduled"),
    claimMonitor(monitor.id, a.id, "scheduled"),
  ]);
  expect(claims.filter(Boolean)).toHaveLength(1);
  await expect(claimMonitor(monitor.id, b.id, "manual")).rejects.toThrow(
    "not found",
  );
  const claim = claims.find(Boolean)!;
  await finishMonitor(monitor.id, claim.run.id, "done");
  await finishMonitor(monitor.id, claim.run.id, "done");
  expect((await loadWorkspace()).notifications).toHaveLength(1);
  expect(deliverPush).toHaveBeenCalledTimes(1);
  await setMonitorEnabled(monitor.id, a.id, false);
  expect(
    await claimMonitor(
      monitor.id,
      a.id,
      "scheduled",
      new Date("2030-01-01T00:00:00Z"),
    ),
  ).toBeNull();
  const saved = await loadWorkspace();
  expect(saved.monitors![0].runs[0].status).toBe("done");
  expect(saved.chats.find((c) => c.id === monitor.chatId)?.caseId).toBe(a.id);
});
test("restart records interrupted runs and skips missed schedules without replaying a backlog", async () => {
  const c = await createCase("SYNTHETIC restart", "");
  const m = await createMonitor({
    caseId: c.id,
    title: "SYNTHETIC restart",
    prompt: "SYNTHETIC",
    cron: "* * * * *",
    timezone: "UTC",
  });
  await claimMonitor(m.id, c.id, "manual");
  await mutateWorkspace((data) => {
    data.monitors![0].nextRunAt = "2020-01-01T00:00:00Z";
  });
  const now = new Date("2026-09-08T08:00:00Z");
  await recoverMonitors(now);
  const saved = (await loadWorkspace()).monitors![0];
  expect(saved.runs[0].status).toBe("skipped");
  expect(saved.runs[1].status).toBe("error");
  expect(Date.parse(saved.nextRunAt)).toBeGreaterThan(now.getTime());
});
