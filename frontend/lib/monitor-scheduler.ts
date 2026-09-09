import { startRun, isChatRunning } from "./codex";
import { loadWorkspace } from "./store";
import { claimMonitor, finishMonitor, recoverMonitors } from "./monitors";
import type { MonitorRun } from "./chat-types";

type SchedulerState = {
  ready: Promise<void>;
  clock?: ReturnType<typeof setInterval>;
  ticking?: boolean;
  lastTickAt?: string;
  error?: string;
};
const shared = globalThis as typeof globalThis & {
  caseMonitorScheduler?: SchedulerState;
};

export async function runMonitor(
  id: string,
  caseId: string,
  trigger: MonitorRun["trigger"],
) {
  const pending = (await loadWorkspace()).monitors?.find(
    (m) => m.id === id && m.caseId === caseId,
  );
  const claimed = await claimMonitor(
    id,
    caseId,
    trigger,
    new Date(),
    pending ? isChatRunning(pending.chatId) : false,
  );
  if (!claimed) return null;
  const { monitor, run } = claimed;
  try {
    const active = await startRun(
      monitor.chatId,
      `Scheduled case review: ${monitor.title}\nCheck time: ${run.at}\n\n${monitor.prompt}\n\nReview only this case and its specified public references using read-only tools. Compare with earlier checks in this monitoring conversation. State changes, what remains unverified, and cite sources. An unsuccessful fetch is not evidence of no change. Report here; do not contact anyone or create more schedules.`,
      "normal",
    );
    await finishMonitor(id, run.id, "running", undefined, active.message.id);
    void active.completion
      .then((message) =>
        finishMonitor(id, run.id, message.status, message.error, message.id),
      )
      .catch(() => {
        if (shared.caseMonitorScheduler)
          shared.caseMonitorScheduler.error =
            "A monitoring result could not be saved.";
      });
    return { runId: run.id, chatId: monitor.chatId };
  } catch (error) {
    await finishMonitor(id, run.id, "error", (error as Error).message);
    throw error;
  }
}

export function ensureMonitorScheduler() {
  if (shared.caseMonitorScheduler) return shared.caseMonitorScheduler.ready;
  const state: SchedulerState = { ready: Promise.resolve() };
  shared.caseMonitorScheduler = state;
  state.ready = recoverMonitors()
    .then(() => {
      // Evaluate persisted cron deadlines instead of trusting a timer to fire
      // exactly on a minute boundary. Docker timers can wake early or late.
      state.clock = setInterval(async () => {
        if (state.ticking) return;
        state.ticking = true;
        try {
          const data = await loadWorkspace();
          state.lastTickAt = new Date().toISOString();
          delete state.error;
          for (const monitor of data.monitors || []) {
            if (!monitor.enabled || Date.parse(monitor.nextRunAt) > Date.now())
              continue;
            try {
              await runMonitor(monitor.id, monitor.caseId, "scheduled");
            } catch {
              /* Failed launches are saved in the run history. Other jobs may proceed. */
            }
          }
        } catch {
          state.error = "The scheduler could not read the saved schedules.";
        } finally {
          state.ticking = false;
        }
      }, 5000);
      state.clock.unref();
    })
    .catch(() => {
      state.error =
        "Monitoring could not start. Check local storage and restart the app.";
    });
  return state.ready;
}

export function schedulerStatus() {
  const state = shared.caseMonitorScheduler;
  return {
    running: !!state?.clock,
    lastTickAt: state?.lastTickAt,
    error: state?.error,
  };
}
