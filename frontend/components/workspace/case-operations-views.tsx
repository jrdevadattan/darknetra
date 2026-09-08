"use client";

import { useState, type FormEvent } from "react";
import {
  Activity,
  Bell,
  Download as DownloadIcon,
  FileArchive,
  Pause,
  Play,
  Plus,
  Radar,
  ShieldAlert,
} from "lucide-react";
import { can, writable } from "@/lib/permissions";
import { download, useApi, usePaged } from "@/lib/api";
import type { Page, S } from "@/lib/types";
import {
  Button,
  EmptyState,
  ErrorBanner,
  EvidenceChip,
  Field,
  LoadMore,
  Loading,
  Modal,
  PanelHeader,
  StatusBadge,
  date,
} from "./shared";
import {
  DEFAULT_SOURCES,
  FormFeedback,
  ITEM_TYPES,
  humanize,
  splitList,
  useCaseAction,
} from "./case-forms";

type ViewProps = {
  caseData: S<"Case">;
  user: S<"UserMe">;
  onEvidence: (id: string) => void;
};

function knownState(state: Record<string, unknown>) {
  const suspended =
    typeof state.suspended_until === "string"
      ? `Suspended until ${date(state.suspended_until)}`
      : null;
  const backoff =
    typeof state.backoff_until === "string"
      ? `Backoff until ${date(state.backoff_until)}`
      : null;
  const reason =
    typeof state.last_error === "string"
      ? state.last_error
      : typeof state.suspension_reason === "string"
        ? state.suspension_reason
        : null;
  const sourceBackoff =
    state.source_backoff && typeof state.source_backoff === "object"
      ? Object.keys(state.source_backoff).length
      : 0;
  const failureCount =
    state.failure_counts && typeof state.failure_counts === "object"
      ? Object.values(state.failure_counts).reduce(
          (sum, value) => sum + (typeof value === "number" ? value : 0),
          0,
        )
      : 0;
  return [
    suspended,
    backoff,
    reason,
    sourceBackoff
      ? `${sourceBackoff} source backoff${sourceBackoff === 1 ? "" : "s"}`
      : null,
    failureCount
      ? `${failureCount} consecutive source failure${failureCount === 1 ? "" : "s"}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function sourceAttemptSummary(sources: Record<string, unknown>) {
  return Object.entries(sources).map(([source, value]) => {
    const status =
      value &&
      typeof value === "object" &&
      "status" in value &&
      typeof value.status === "string"
        ? value.status
        : "ATTEMPTED";
    return `${source}: ${status}`;
  });
}

function runErrorSummary(errors: Record<string, unknown>) {
  return Object.entries(errors).map(([source, value]) => {
    if (!value || typeof value !== "object") return `${source}: source failed`;
    const code =
      "code" in value && typeof value.code === "string" ? value.code : "ERROR";
    const message =
      "message" in value && typeof value.message === "string"
        ? value.message
        : "Source failed";
    return `${source}: ${code} — ${message}`;
  });
}

export function MonitoringView({ caseData, user }: ViewProps) {
  const watchlists = usePaged<S<"Watchlist">>(
    `/cases/${caseData.id}/watchlists`,
  );
  const [selected, setSelected] = useState<string | null>(null);
  const selectedId = selected ?? watchlists.items[0]?.id ?? null;
  const items = usePaged<S<"WatchlistItem">>(
    selectedId ? `/cases/${caseData.id}/watchlists/${selectedId}/items` : null,
    5000,
  );
  const runs = useApi<Page<S<"MonitorRun">>>(
    `/cases/${caseData.id}/monitor/runs?limit=50`,
    5_000,
  );
  const action = useCaseAction(caseData.id);
  const [watchlistOpen, setWatchlistOpen] = useState(false);
  const [itemOpen, setItemOpen] = useState(false);
  const [itemType, setItemType] =
    useState<S<"WatchlistItemIn">["type"]>("KEYWORD");

  async function createWatchlist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const name = String(new FormData(form).get("name"));
    const result = await action.run<S<"Watchlist">>(
      `/cases/${caseData.id}/watchlists`,
      "POST",
      { name } satisfies S<"WatchlistCreate">,
      "Watchlist created",
    );
    if (result) {
      setSelected(result.id);
      setWatchlistOpen(false);
      form.reset();
    }
  }

  async function createItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const body: S<"WatchlistItemIn"> = {
      type: itemType,
      value: String(data.get("value")),
      variants: splitList(String(data.get("variants") || "")),
      sources: splitList(String(data.get("sources") || "")),
      interval_seconds: Number(data.get("interval_seconds")),
      active: true,
      note: String(data.get("note") || "") || null,
    };
    const result = await action.run<S<"WatchlistItem">>(
      `/cases/${caseData.id}/watchlists/${selectedId}/items`,
      "POST",
      body,
      "Monitoring item created",
    );
    if (result) {
      setItemOpen(false);
      form.reset();
    }
  }

  async function toggleItem(item: S<"WatchlistItem">) {
    await action.run<S<"WatchlistItem">>(
      `/cases/${caseData.id}/watchlists/${item.watchlist_id}/items/${item.id}`,
      "PATCH",
      { active: !item.active } satisfies S<"WatchlistItemPatch">,
      item.active ? "Item paused" : "Item resumed",
    );
  }

  async function runNow(item: S<"WatchlistItem">) {
    await action.run<S<"MonitorRun">>(
      `/cases/${caseData.id}/watchlists/${item.watchlist_id}/items/${item.id}/run`,
      "POST",
      undefined,
      "Monitoring attempt finished",
    );
    await runs.refetch();
  }

  return (
    <div className="content-stack">
      <PanelHeader
        title="Monitoring"
        description="Scheduled, read-only checks with captured evidence, rate limits, and visible failures."
      >
        {writable(user, caseData) ? (
          <Button
            variant="outline"
            onClick={() => {
              action.clear();
              setWatchlistOpen(true);
            }}
          >
            <Plus size={15} />
            Watchlist
          </Button>
        ) : null}
      </PanelHeader>
      {!caseData.source_policy.tor_enabled ? (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-200">
          <ShieldAlert size={16} className="mr-2 inline" />
          Tor collection is disabled by case policy. Monitoring attempts will
          report unavailable dark sources instead of silently skipping them.
        </div>
      ) : null}
      <div className="grid gap-4 xl:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="panel-card self-start">
          <div className="flex items-center justify-between">
            <h2>Watchlists</h2>
          </div>
          <ErrorBanner error={watchlists.error} />
          {watchlists.isLoading ? (
            <Loading label="Loading watchlists" />
          ) : watchlists.items.length ? (
            <nav className="mt-3 space-y-1" aria-label="Watchlists">
              {watchlists.items.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setSelected(item.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm ${selectedId === item.id ? "bg-accent text-accent-foreground" : "hover:bg-accent/50"}`}
                >
                  <span className="block truncate">{item.name}</span>
                  <span className="muted text-xs">
                    {item.active ? "Active" : "Inactive"}
                  </span>
                </button>
              ))}
            </nav>
          ) : (
            <p className="muted mt-3 text-sm">No watchlists.</p>
          )}
        </aside>
        <section className="panel-card">
          <div className="flex items-center justify-between gap-3">
            <h2>Monitored items</h2>
            {selectedId && writable(user, caseData) ? (
              <Button
                size="sm"
                onClick={() => {
                  action.clear();
                  setItemOpen(true);
                }}
              >
                <Plus size={14} />
                Add item
              </Button>
            ) : null}
          </div>
          <FormFeedback
            busy={action.busy}
            error={action.error}
            message={action.message}
          />
          <ErrorBanner error={items.error} />
          {items.isLoading ? (
            <Loading label="Loading monitoring items" />
          ) : items.items.length ? (
            <div className="mt-4 space-y-3">
              {items.items.map((item) => (
                <article
                  className="rounded-xl border border-border p-4"
                  key={item.id}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <span className="muted text-xs uppercase">
                        {humanize(item.type)}
                      </span>
                      <h3 className="mt-1 text-sm">{item.value}</h3>
                      <p className="muted mt-1 text-xs">
                        Every {Math.round(item.interval_seconds / 60)} min ·{" "}
                        {item.sources?.join(", ") || "Backend defaults"}
                      </p>
                    </div>
                    <StatusBadge status={item.active ? "ACTIVE" : "PAUSED"} />
                  </div>
                  {knownState(item.state) ? (
                    <p className="mt-3 text-xs text-amber-300">
                      {knownState(item.state)}
                    </p>
                  ) : null}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {writable(user, caseData) ? (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void toggleItem(item)}
                        >
                          {item.active ? (
                            <Pause size={13} />
                          ) : (
                            <Play size={13} />
                          )}{" "}
                          {item.active ? "Pause" : "Resume"}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void runNow(item)}
                        >
                          <Radar size={13} />
                          Run now
                        </Button>
                      </>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No monitoring items"
              description="Add an authorised keyword, alias, wallet, fingerprint, locator, channel, or image hash."
              icon={<Radar size={23} />}
            />
          )}
          <LoadMore {...items} />
        </section>
      </div>
      <section className="panel-card">
        <h2 className="flex items-center gap-2">
          <Activity size={17} />
          Recent attempts
        </h2>
        <ErrorBanner error={runs.error} retry={() => void runs.refetch()} />
        {runs.isLoading ? (
          <Loading label="Loading monitoring attempts" />
        ) : runs.data?.items.length ? (
          <div className="table-wrap mt-4">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Status</th>
                  <th>Sources attempted</th>
                  <th>New hits</th>
                  <th>Errors</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.items.map((run) => (
                  <tr key={run.id}>
                    <td>{date(run.started_at)}</td>
                    <td>
                      <StatusBadge status={run.status} />
                    </td>
                    <td>
                      {sourceAttemptSummary(run.sources_run).length ? (
                        <ul className="space-y-1 text-xs">
                          {sourceAttemptSummary(run.sources_run).map(
                            (source) => (
                              <li key={source}>{source}</li>
                            ),
                          )}
                        </ul>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>{run.new_hits}</td>
                    <td
                      className={
                        Object.keys(run.errors).length
                          ? "text-red-400"
                          : "muted"
                      }
                    >
                      {runErrorSummary(run.errors).length ? (
                        <ul className="space-y-1 text-xs">
                          {runErrorSummary(run.errors).map((error) => (
                            <li key={error}>{error}</li>
                          ))}
                        </ul>
                      ) : (
                        "None"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No attempts recorded"
            description="Manual and scheduled monitoring runs will appear here, including failures."
            icon={<Activity size={23} />}
          />
        )}
      </section>

      <Modal
        open={watchlistOpen}
        onClose={() => setWatchlistOpen(false)}
        title="Create watchlist"
      >
        <form
          className="content-stack"
          onSubmit={(event) => void createWatchlist(event)}
        >
          <Field label="Name">
            <input required name="name" maxLength={200} />
          </Field>
          <FormFeedback busy={action.busy} error={action.error} />
          <Button disabled={action.busy} type="submit">
            Create watchlist
          </Button>
        </form>
      </Modal>
      <Modal
        open={itemOpen}
        onClose={() => setItemOpen(false)}
        title="Add monitoring item"
        description="Sources are read-only adapters governed by this case policy."
      >
        <form
          className="content-stack"
          onSubmit={(event) => void createItem(event)}
        >
          <Field label="Type">
            <select
              value={itemType}
              onChange={(event) =>
                setItemType(event.target.value as typeof itemType)
              }
            >
              {ITEM_TYPES.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </Field>
          <Field label="Value">
            <input required name="value" />
          </Field>
          <Field
            label="Variants"
            hint="Optional comma- or line-separated alternatives."
          >
            <textarea name="variants" rows={3} />
          </Field>
          <Field
            label="Sources"
            hint="Only configured backend source adapters will run."
          >
            <textarea
              key={itemType}
              required
              name="sources"
              rows={3}
              defaultValue={DEFAULT_SOURCES[itemType].join(", ")}
            />
          </Field>
          <Field label="Interval (seconds)" hint="Minimum 60 seconds.">
            <input
              required
              name="interval_seconds"
              type="number"
              min={60}
              defaultValue={21600}
            />
          </Field>
          <Field label="Analyst note">
            <textarea name="note" rows={3} />
          </Field>
          <FormFeedback busy={action.busy} error={action.error} />
          <Button disabled={action.busy} type="submit">
            Add item
          </Button>
        </form>
      </Modal>
    </div>
  );
}

type AlertAction = {
  alert: S<"Alert">;
  action: "ack" | "dismiss" | "escalate";
};

export function AlertsView({ caseData, user, onEvidence }: ViewProps) {
  const [status, setStatus] = useState("");
  const alerts = usePaged<S<"Alert">>(
    `/cases/${caseData.id}/alerts${status ? `?status=${status}` : ""}`,
  );
  const action = useCaseAction(caseData.id);
  const [selected, setSelected] = useState<AlertAction | null>(null);
  async function handle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const rationale = String(
      new FormData(event.currentTarget).get("rationale"),
    );
    const result = await action.run<unknown>(
      `/cases/${caseData.id}/alerts/${selected.alert.id}/${selected.action}`,
      "POST",
      { rationale },
      `Alert ${selected.action === "ack" ? "acknowledged" : selected.action === "dismiss" ? "dismissed" : "escalated"}`,
    );
    if (result) setSelected(null);
  }
  return (
    <div className="content-stack">
      <PanelHeader
        title="Alerts"
        description="Evidence-backed monitoring events awaiting a human disposition."
      />
      <section className="panel-card">
        <div className="max-w-xs">
          <Field label="Status">
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All alerts</option>
              {["OPEN", "ACKNOWLEDGED", "DISMISSED", "ESCALATED"].map(
                (item) => (
                  <option key={item}>{item}</option>
                ),
              )}
            </select>
          </Field>
        </div>
        <ErrorBanner error={alerts.error} retry={() => void alerts.refetch()} />
        {alerts.isLoading ? (
          <Loading label="Loading alerts" />
        ) : alerts.items.length ? (
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            {alerts.items.map((alert) => (
              <article
                className="rounded-xl border border-border p-4"
                key={alert.id}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <StatusBadge status={alert.status} />
                  <span className="muted text-xs">
                    {humanize(alert.kind)} · {date(alert.at)}
                  </span>
                </div>
                <h2 className="mt-3 text-base">{alert.title}</h2>
                <p className="mt-2 text-sm leading-6">{alert.summary}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {alert.evidence.map((item) => (
                    <EvidenceChip
                      key={item.id}
                      code={item.code}
                      onClick={() => onEvidence(item.id)}
                    />
                  ))}
                </div>
                {alert.decision ? (
                  <p className="muted mt-3 text-xs">
                    {alert.decision.decided_by.display}:{" "}
                    {alert.decision.rationale}
                  </p>
                ) : null}
                {alert.status === "OPEN" && writable(user, caseData) ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        action.clear();
                        setSelected({ alert, action: "ack" });
                      }}
                    >
                      Acknowledge
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        action.clear();
                        setSelected({ alert, action: "dismiss" });
                      }}
                    >
                      Dismiss
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => {
                        action.clear();
                        setSelected({ alert, action: "escalate" });
                      }}
                    >
                      Escalate
                    </Button>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No alerts found"
            description="No alerts match the current status filter."
            icon={<Bell size={23} />}
          />
        )}
        <LoadMore {...alerts} />
      </section>
      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={`${selected ? humanize(selected.action) : "Handle"} alert`}
        description="A rationale is required and becomes part of the decision record."
      >
        <form
          className="content-stack"
          onSubmit={(event) => void handle(event)}
        >
          <p className="text-sm">{selected?.alert.title}</p>
          <Field label="Rationale">
            <textarea required name="rationale" rows={5} />
          </Field>
          <FormFeedback busy={action.busy} error={action.error} />
          <Button disabled={action.busy} type="submit">
            Record {selected ? humanize(selected.action) : "action"}
          </Button>
        </form>
      </Modal>
    </div>
  );
}

const REPORT_SECTIONS = [
  "cover",
  "scope",
  "evidence",
  "observations",
  "links",
  "activity",
  "wallets",
  "graph",
  "timeline",
  "alerts",
  "decisions",
  "methods",
  "limitations",
  "appendix",
];
type ReportFormat = "md" | "html" | "pdf" | "zip" | "sha256" | "manifest";

export function ReportsView({ caseData, user, onEvidence }: ViewProps) {
  const reports = useApi<Page<S<"Report">>>(
    `/cases/${caseData.id}/reports?limit=50`,
    5_000,
  );
  const action = useCaseAction(caseData.id);
  const [open, setOpen] = useState(false);
  const [downloadError, setDownloadError] = useState<unknown>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const canGenerate = can(user, caseData, "write");
  const canExport = can(user, caseData, "export");
  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const result = await action.run<S<"ReportJob">>(
      `/cases/${caseData.id}/reports`,
      "POST",
      {
        sections: data.getAll("sections").map(String),
        redact: !canExport || data.get("redact") === "on",
        include_appendix: data.get("include_appendix") === "on",
        narrative: data.get("narrative") === "on",
        window: null,
      } satisfies S<"ReportRequest">,
      "Report queued",
    );
    if (result) {
      setOpen(false);
      await reports.refetch();
    }
  }
  async function getReport(report: S<"Report">, format: ReportFormat) {
    setDownloading(`${report.id}-${format}`);
    setDownloadError(null);
    try {
      await download(
        `/cases/${caseData.id}/reports/${report.id}/download?format=${format}`,
        `${caseData.code}-report-v${report.version}.${format === "zip" ? "zip" : format}`,
      );
    } catch (caught) {
      setDownloadError(caught);
    } finally {
      setDownloading(null);
    }
  }
  return (
    <div className="content-stack">
      <PanelHeader
        title="Investigation packs"
        description="Versioned reports generated from persisted store sections with claim checks and immutable hashes."
      >
        {canGenerate ? (
          <Button
            onClick={() => {
              action.clear();
              setOpen(true);
            }}
          >
            <Plus size={15} />
            Generate report
          </Button>
        ) : null}
      </PanelHeader>
      <ErrorBanner error={reports.error} retry={() => void reports.refetch()} />
      <ErrorBanner error={downloadError} />
      {reports.isLoading ? (
        <Loading label="Loading reports" />
      ) : reports.data?.items.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {reports.data.items.map((report) => {
            const unredacted = report.redaction.applied === false;
            return (
              <article className="panel-card" key={report.id}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <StatusBadge status={report.status} />
                  <span className="muted text-xs">
                    v{report.version} · {date(report.at)}
                  </span>
                </div>
                <h2 className="mt-3">Investigation pack</h2>
                <p className="muted mt-1 text-sm">
                  {unredacted ? "Unredacted" : "Role-based redaction applied"} ·{" "}
                  {report.claim_check.claims} claims checked
                </p>
                {report.claim_check.unverified_dropped ? (
                  <p className="mt-2 text-sm text-amber-300">
                    {report.claim_check.unverified_dropped} unverified claim
                    {report.claim_check.unverified_dropped === 1
                      ? ""
                      : "s"}{" "}
                    dropped.
                  </p>
                ) : null}
                {report.sha256 ? (
                  <p className="muted mt-3 break-all font-mono text-xs">
                    SHA-256 {report.sha256}
                  </p>
                ) : null}
                {report.evidence ? (
                  <div className="mt-3">
                    <EvidenceChip
                      code={report.evidence.code}
                      onClick={() => onEvidence(report.evidence!.id)}
                    />
                  </div>
                ) : null}
                {report.status === "DONE" &&
                canGenerate &&
                (!unredacted || canExport) ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {(
                      [
                        "md",
                        "html",
                        "pdf",
                        "zip",
                        "sha256",
                        "manifest",
                      ] as ReportFormat[]
                    ).map((format) => (
                      <Button
                        size="sm"
                        variant="outline"
                        key={format}
                        disabled={downloading === `${report.id}-${format}`}
                        onClick={() => void getReport(report, format)}
                      >
                        <DownloadIcon size={13} />
                        {format === "zip"
                          ? "Appendix bundle"
                          : format.toUpperCase()}
                      </Button>
                    ))}
                  </div>
                ) : report.status === "DONE" && unredacted && !canExport ? (
                  <p className="muted mt-4 text-xs">
                    Export permission is required to download this unredacted
                    report.
                  </p>
                ) : report.status === "DONE" && !canGenerate ? (
                  <p className="muted mt-4 text-xs">
                    Report generation permission is required to download this
                    pack.
                  </p>
                ) : (
                  <p className="muted mt-4 text-xs">
                    Status refreshes every five seconds.
                  </p>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title="No reports generated"
          description="Generate a versioned pack when the case record is ready for review."
          icon={<FileArchive size={23} />}
        />
      )}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Generate investigation pack"
        description="Narrative sections pass the claim checker; unverified sentences are dropped."
      >
        <form
          className="content-stack"
          onSubmit={(event) => void generate(event)}
        >
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Sections</legend>
            <div className="grid grid-cols-2 gap-2 rounded-lg border border-border p-3">
              {REPORT_SECTIONS.map((section) => (
                <label
                  className="flex items-center gap-2 text-sm"
                  key={section}
                >
                  <input
                    defaultChecked
                    type="checkbox"
                    name="sections"
                    value={section}
                  />
                  {humanize(section)}
                </label>
              ))}
            </div>
          </fieldset>
          {canExport ? (
            <label className="flex items-center gap-2 text-sm">
              <input defaultChecked type="checkbox" name="redact" />
              Apply role-based redaction
            </label>
          ) : (
            <p className="muted text-sm">
              Role-based redaction is required for your case role.
            </p>
          )}
          <label className="flex items-center gap-2 text-sm">
            <input defaultChecked type="checkbox" name="include_appendix" />
            Include evidence appendix
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input defaultChecked type="checkbox" name="narrative" />
            Generate checked narrative
          </label>
          <FormFeedback busy={action.busy} error={action.error} />
          <Button disabled={action.busy} type="submit">
            Queue report
          </Button>
        </form>
      </Modal>
    </div>
  );
}
