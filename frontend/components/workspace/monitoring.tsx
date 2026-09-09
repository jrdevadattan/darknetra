"use client";
import { useLanguage } from "./language";
import { useCallback, useEffect, useState } from "react";
import { Clock3, LoaderCircle, Pause, Play, Plus } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { CaseMonitor } from "@/lib/chat-types";
import {
  SchedulePicker,
  scheduleExpression,
  scheduleDescription,
  type ScheduleChoice,
} from "./schedule-picker";

type State = {
  monitors: CaseMonitor[];
  scheduler: { running: boolean; error?: string; lastTickAt?: string };
};
function date(value: string, timezone: string) {
  return new Date(value).toLocaleString([], {
    timeZone: timezone,
    dateStyle: "medium",
    timeStyle: "short",
  });
}
export function CaseMonitoring({
  caseId,
  onOpenChat,
  onChange,
}: {
  caseId: string | null;
  onOpenChat: (chatId: string) => void;
  onChange: () => Promise<void>;
}) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<State>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [schedule, setSchedule] = useState<ScheduleChoice>({
    repeat: "daily",
    time: "09:00",
    days: [0, 1, 2, 3, 4, 5, 6],
    interval: "15",
    intervalUnit: "minutes",
    weeklyDay: 1,
  });
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener("darknetra-open-monitoring", show);
    return () => window.removeEventListener("darknetra-open-monitoring", show);
  }, []);
  const refresh = useCallback(async () => {
    if (!caseId) return;
    try {
      const response = await fetch(
        `/api/monitors?caseId=${encodeURIComponent(caseId)}`,
        { cache: "no-store" },
      );
      const value = await response.json();
      if (!response.ok) throw new Error(value.error);
      setData(value);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }, [caseId]);
  useEffect(() => {
    setData(undefined);
    setError("");
    setAdding(false);
  }, [caseId]);
  useEffect(() => {
    if (!open) return;
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [open, refresh]);
  async function action(body: Record<string, unknown>) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/monitors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, caseId }),
      });
      const value = await response.json();
      if (!response.ok) throw new Error(value.error);
      if (body.action === "create") {
        setAdding(false);
        setTitle("");
        setPrompt("");
      }
      await refresh();
      await onChange();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          className="icon-button"
          aria-label={t("Case monitoring")}
          title={t("Case monitoring")}
        >
          <Clock3 size={18} />
        </button>
      </DialogTrigger>
      <DialogContent className="monitor-dialog">
        <DialogHeader>
          <DialogTitle>{t("Case monitoring")}</DialogTitle>
          <DialogDescription>
            Schedule repeat checks and review their results here.
          </DialogDescription>
        </DialogHeader>
        {!caseId ? (
          <p className="muted">
            Open or create a case to add a monitoring schedule.
          </p>
        ) : (
          <>
            <p className="monitor-note">
              Checks run while the Docker app is running, even when this browser
              is closed. Each check uses your connected assistant account.
            </p>
            {data && (
              <p className="scheduler-state">
                {data.scheduler.running
                  ? "Scheduler active"
                  : "Scheduler unavailable"}
                {data.scheduler.error ? ` · ${data.scheduler.error}` : ""}
              </p>
            )}
            {error && (
              <p role="alert" className="error-banner">
                {error}
              </p>
            )}
            {!data && !error && <LoaderCircle className="spin" size={18} />}
            {data?.monitors.map((monitor) => (
              <article className="monitor-card" key={monitor.id}>
                <header>
                  <strong>{monitor.title}</strong>
                  <span>{monitor.enabled ? "Scheduled" : t("Paused")}</span>
                </header>
                <p className="monitor-prompt">{monitor.prompt}</p>
                <p>
                  {scheduleDescription(monitor.cron)} · {monitor.timezone}
                </p>
                <p className="muted">
                  {monitor.enabled
                    ? `Next check: ${date(monitor.nextRunAt, monitor.timezone)}`
                    : "Automatic checks are paused."}
                </p>
                <div className="monitor-actions">
                  <button
                    disabled={busy}
                    onClick={() =>
                      void action({
                        action: "toggle",
                        id: monitor.id,
                        enabled: !monitor.enabled,
                      })
                    }
                  >
                    {monitor.enabled ? <Pause size={13} /> : <Play size={13} />}
                    {monitor.enabled ? t("Pause") : t("Resume")}
                  </button>
                  <button
                    disabled={
                      busy ||
                      monitor.runs.some((run) => run.status === "running")
                    }
                    onClick={() =>
                      void action({ action: "run", id: monitor.id })
                    }
                  >
                    <Play size={13} />
                    {t("Run now")}
                  </button>
                  <button
                    onClick={() => {
                      onOpenChat(monitor.chatId);
                      setOpen(false);
                    }}
                  >
                    Open results
                  </button>
                </div>
                <details
                  className="monitor-history"
                  open={monitor.runs.length > 0}
                >
                  <summary>Run history ({monitor.runs.length})</summary>
                  {!monitor.runs.length && <p>No checks have run yet.</p>}
                  <ol>
                    {monitor.runs.slice(0, 20).map((run) => (
                      <li key={run.id}>
                        <span className={`monitor-run-status ${run.status}`}>
                          {run.status === "running" && (
                            <LoaderCircle size={12} className="spin" />
                          )}
                          {run.status === "done"
                            ? t("Completed")
                            : run.status.charAt(0).toUpperCase() +
                              run.status.slice(1)}
                        </span>
                        <time>{date(run.at, monitor.timezone)}</time>
                        <small>
                          {run.trigger === "scheduled"
                            ? "Scheduled check"
                            : run.trigger === "chat"
                              ? "Requested in chat"
                              : "Manual check"}
                        </small>
                        {run.error && <p>{run.error}</p>}
                      </li>
                    ))}
                  </ol>
                  {monitor.runs.length > 20 && (
                    <p>
                      Showing the latest 20 runs. Earlier results remain in the
                      monitoring chat.
                    </p>
                  )}
                </details>
              </article>
            ))}
            {adding || data?.monitors.length === 0 ? (
              <form
                className="monitor-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void action({
                    action: "create",
                    title,
                    prompt,
                    cron: scheduleExpression(schedule),
                    timezone,
                  });
                }}
              >
                <label>
                  {t("Schedule name")}
                  <input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    maxLength={120}
                    required
                    placeholder="Daily reference review"
                  />
                </label>
                <label>
                  What should be checked?
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    maxLength={8000}
                    required
                    rows={3}
                    placeholder="Specify the public references and changes to check."
                  />
                </label>
                <SchedulePicker
                  value={schedule}
                  onChange={setSchedule}
                  timezone={timezone}
                  onTimezoneChange={setTimezone}
                />
                <div className="monitor-actions">
                  <button
                    className="primary-button"
                    disabled={
                      busy ||
                      !title.trim() ||
                      !prompt.trim() ||
                      !scheduleExpression(schedule)
                    }
                  >
                    {busy ? t("Saving…") : t("Save schedule")}
                  </button>
                  {adding && (
                    <button type="button" onClick={() => setAdding(false)}>
                      {t("Cancel")}
                    </button>
                  )}
                </div>
              </form>
            ) : (
              data && (
                <button className="monitor-add" onClick={() => setAdding(true)}>
                  <Plus size={15} />
                  {t("Add schedule")}
                </button>
              )
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
