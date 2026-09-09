import { randomUUID } from "node:crypto";
import { Cron } from "croner";
import { loadWorkspace, mutateWorkspace } from "./store";
import type { CaseMonitor, MonitorRun, WorkspaceData } from "./chat-types";
import { deliverPush } from "./push";

export function nextOccurrence(
  expression: string,
  timezone: string,
  after = new Date(),
) {
  if (expression.trim().split(/\s+/).length !== 5 || expression.length > 120)
    throw new Error(
      "Use a five-field cron expression: minute hour day month weekday.",
    );
  try {
    new Intl.DateTimeFormat("en", { timeZone: timezone }).format(after);
    const cron = new Cron(expression.trim(), { timezone, paused: true });
    const next = cron.nextRun(after);
    cron.stop();
    if (!next) throw new Error();
    return next.toISOString();
  } catch {
    throw new Error(
      "Enter a valid cron schedule and timezone with a future run.",
    );
  }
}

function findMonitor(data: WorkspaceData, id: string, caseId: string) {
  const monitor = data.monitors?.find(
    (m) => m.id === id && m.caseId === caseId,
  );
  if (
    !monitor ||
    !data.cases.some((c) => c.id === caseId) ||
    !data.chats.some((c) => c.id === monitor.chatId && c.caseId === caseId)
  )
    throw new Error("Monitor not found");
  return monitor;
}

export async function createMonitor(
  input: Pick<CaseMonitor, "caseId" | "title" | "prompt" | "cron" | "timezone">,
) {
  if (
    !input.title.trim() ||
    input.title.length > 120 ||
    !input.prompt.trim() ||
    input.prompt.length > 8000
  )
    throw new Error(
      "Enter a title up to 120 characters and instructions up to 8,000 characters.",
    );
  const nextRunAt = nextOccurrence(input.cron, input.timezone);
  return mutateWorkspace((data) => {
    if (!data.cases.some((c) => c.id === input.caseId))
      throw new Error("Case not found");
    data.monitors ||= [];
    if (data.monitors.length >= 50)
      throw new Error("This workspace supports up to 50 schedules.");
    const chatId = randomUUID();
    const createdAt = new Date().toISOString();
    const monitor: CaseMonitor = {
      ...input,
      title: input.title.trim(),
      prompt: input.prompt.trim(),
      cron: input.cron.trim(),
      id: randomUUID(),
      chatId,
      enabled: true,
      createdAt,
      nextRunAt,
      runs: [],
    };
    data.chats.unshift({
      id: chatId,
      caseId: input.caseId,
      title: `Monitoring: ${monitor.title}`,
      createdAt,
      messages: [],
    });
    data.monitors.unshift(monitor);
    return monitor;
  });
}

export function setMonitorEnabled(
  id: string,
  caseId: string,
  enabled: boolean,
) {
  return mutateWorkspace((data) => {
    const monitor = findMonitor(data, id, caseId);
    monitor.enabled = enabled;
    if (enabled)
      monitor.nextRunAt = nextOccurrence(monitor.cron, monitor.timezone);
    return monitor;
  });
}

export function claimMonitor(
  id: string,
  caseId: string,
  trigger: MonitorRun["trigger"],
  now = new Date(),
  chatBusy = false,
) {
  return mutateWorkspace((data) => {
    const monitor = findMonitor(data, id, caseId);
    if (trigger === "scheduled") {
      if (!monitor.enabled || Date.parse(monitor.nextRunAt) > now.getTime())
        return null;
      monitor.nextRunAt = nextOccurrence(monitor.cron, monitor.timezone, now);
    }
    if (monitor.runs.some((r) => r.status === "running") || chatBusy) {
      if (trigger === "manual")
        throw new Error("This monitor is already running.");
      monitor.runs.unshift({
        id: randomUUID(),
        at: now.toISOString(),
        trigger,
        status: "skipped",
        error: "The previous check is still running.",
      });
      return null;
    }
    const run: MonitorRun = {
      id: randomUUID(),
      at: now.toISOString(),
      trigger,
      status: "running",
    };
    monitor.runs.unshift(run);
    return { monitor, run };
  });
}

export async function finishMonitor(
  id: string,
  runId: string,
  status: MonitorRun["status"],
  error?: string,
  messageId?: string,
) {
  const notification = await mutateWorkspace((data) => {
    const monitor = data.monitors?.find((m) => m.id === id);
    const run = monitor?.runs.find((r) => r.id === runId);
    if (!run) throw new Error("Monitor run not found");
    if (run.finishedAt) return;
    run.status = status;
    run.error = error?.slice(0, 1000);
    if (messageId) run.messageId = messageId;
    if (status !== "running") {
      run.finishedAt = new Date().toISOString();
      const notice = {
        id: run.id,
        at: run.finishedAt,
        kind: status === "done" ? ("complete" as const) : ("error" as const),
        title:
          status === "done"
            ? "Monitoring check complete"
            : "Monitoring needs attention",
        body:
          status === "done"
            ? "A case review is ready. Open DARKNETRA to read the results."
            : "A case check did not finish successfully. Open DARKNETRA to review it.",
        caseId: monitor!.caseId,
        chatId: monitor!.chatId,
      };
      data.notifications ||= [];
      data.notifications.unshift(notice);
      data.notifications = data.notifications.slice(0, 200);
      return notice;
    }
  });
  if (notification) void deliverPush(notification).catch(() => {});
}

export async function recoverMonitors(now = new Date()) {
  const saved = await loadWorkspace();
  if (!saved.monitors?.length) return;
  for (const monitor of saved.monitors)
    for (const run of monitor.runs)
      if (run.status === "running")
        await finishMonitor(
          monitor.id,
          run.id,
          "error",
          "The app restarted during this check. Run it again when ready.",
        );
  await mutateWorkspace((data) => {
    for (const monitor of data.monitors || []) {
      for (const run of monitor.runs)
        if (run.status === "running") {
          run.status = "error";
          run.error =
            "The app restarted during this check. Run it again when ready.";
          run.finishedAt = now.toISOString();
        }
      if (monitor.enabled && Date.parse(monitor.nextRunAt) <= now.getTime()) {
        monitor.runs.unshift({
          id: randomUUID(),
          at: now.toISOString(),
          trigger: "scheduled",
          status: "skipped",
          error:
            "The app was offline at the scheduled time. Missed checks were not replayed.",
        });
        monitor.nextRunAt = nextOccurrence(monitor.cron, monitor.timezone, now);
      }
    }
  });
}
