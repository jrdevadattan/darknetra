"use client";

import { useMemo, useState, type FormEvent } from "react";
import {
  Boxes,
  Database,
  FileSearch,
  Files,
  Search,
  Upload,
  UsersRound,
} from "lucide-react";
import { api, useApi, usePaged } from "@/lib/api";
import type { S } from "@/lib/types";
import { writable } from "@/lib/permissions";
import {
  Button,
  EmptyState,
  ErrorBanner,
  EvidenceChip,
  Field,
  LoadMore,
  Loading,
  PanelHeader,
  StatusBadge,
  date,
} from "./shared";
import {
  FormFeedback,
  SOURCE_CLASSES,
  humanize,
  useCaseAction,
} from "./case-forms";

type ViewProps = {
  caseData: S<"Case">;
  user: S<"UserMe">;
  onEvidence: (id: string) => void;
};

function total(values: Record<string, number>) {
  return Object.values(values).reduce((sum, value) => sum + value, 0);
}

export function OverviewView({ caseData }: ViewProps) {
  const summary = useApi<S<"CaseSummary">>(
    `/cases/${caseData.id}/summary`,
    15_000,
  );
  const timeline = usePaged<S<"TimelineEntry">>(
    `/cases/${caseData.id}/timeline`,
  );
  if (summary.isLoading && !summary.data)
    return <Loading label="Loading case overview" />;
  return (
    <div className="content-stack">
      <PanelHeader
        title="Case overview"
        description="Live counts from the case store and its audited timeline."
      />
      <ErrorBanner error={summary.error} retry={() => void summary.refetch()} />
      {summary.data ? (
        <>
          <div className="metric-grid">
            <article className="metric-card">
              <Files size={18} />
              <strong>
                {total(summary.data.evidence_by_class).toLocaleString()}
              </strong>
              <span>Evidence records</span>
            </article>
            <article className="metric-card">
              <Boxes size={18} />
              <strong>
                {total(summary.data.observations_by_type).toLocaleString()}
              </strong>
              <span>Observations</span>
            </article>
            <article className="metric-card">
              <UsersRound size={18} />
              <strong>
                {summary.data.pending_candidates.toLocaleString()}
              </strong>
              <span>Pending candidates</span>
            </article>
            <article className="metric-card">
              <Database size={18} />
              <strong>{summary.data.open_alerts.toLocaleString()}</strong>
              <span>Open alerts</span>
            </article>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <section className="panel-card">
              <h2>Evidence by source</h2>
              <div className="mt-4 space-y-3">
                {Object.entries(summary.data.evidence_by_class).map(
                  ([key, value]) => (
                    <div
                      className="flex items-center justify-between gap-4"
                      key={key}
                    >
                      <span className="muted text-sm">{humanize(key)}</span>
                      <strong>{value}</strong>
                    </div>
                  ),
                )}
              </div>
            </section>
            <section className="panel-card">
              <h2>Evidence health</h2>
              <div className="mt-4 space-y-3">
                {Object.entries(summary.data.evidence_by_status).map(
                  ([key, value]) => (
                    <div
                      className="flex items-center justify-between gap-4"
                      key={key}
                    >
                      <StatusBadge status={key} />
                      <strong>{value}</strong>
                    </div>
                  ),
                )}
              </div>
            </section>
            <section className="panel-card">
              <h2>Workspace pulse</h2>
              <dl className="mt-4 space-y-3 text-sm">
                <div className="flex justify-between">
                  <dt className="muted">Active monitors</dt>
                  <dd>{summary.data.active_items}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="muted">Investigation threads</dt>
                  <dd>{summary.data.threads}</dd>
                </div>
                <div>
                  <dt className="muted">Last audited activity</dt>
                  <dd className="mt-1">
                    {date(summary.data.last_activity_at)}
                  </dd>
                </div>
              </dl>
            </section>
          </div>
        </>
      ) : null}
      <section className="panel-card">
        <h2>Recent timeline</h2>
        <ErrorBanner
          error={timeline.error}
          retry={() => void timeline.refetch()}
        />
        {timeline.isLoading ? (
          <Loading label="Loading timeline" />
        ) : timeline.items.length ? (
          <ol className="mt-4 space-y-4 border-l border-border pl-5">
            {timeline.items.map((entry, index) => (
              <li key={`${entry.at}-${entry.ref.id}-${index}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <strong className="text-sm">{humanize(entry.title)}</strong>
                  <span className="muted text-xs">
                    {humanize(entry.ref.type)}
                  </span>
                </div>
                <p className="muted mt-1 text-xs">
                  {date(entry.at)}
                  {entry.actor ? ` · ${entry.actor.display}` : ""}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState
            title="No timeline entries"
            description="Audited case activity will appear here."
          />
        )}
        <LoadMore {...timeline} />
      </section>
    </div>
  );
}

export function EvidenceView({ caseData, user, onEvidence }: ViewProps) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [sourceClass, setSourceClass] = useState("");
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (status) params.set("status", status);
  if (sourceClass) params.set("source_class", sourceClass);
  const evidence = usePaged<S<"Evidence">>(
    `/cases/${caseData.id}/evidence${params.size ? `?${params}` : ""}`,
    5000,
  );
  const action = useCaseAction(caseData.id);
  const [uploadResult, setUploadResult] = useState<S<"UploadResponse"> | null>(
    null,
  );
  const allowedSources = SOURCE_CLASSES.filter(
    (item) =>
      caseData.source_policy.allowed_source_classes.includes(item) &&
      (caseData.demo || item !== "SYNTHETIC"),
  );

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    if (!caseData.demo || data.get("source_class") !== "SYNTHETIC")
      data.delete("source_family");
    const result = await action.run<S<"UploadResponse">>(
      `/cases/${caseData.id}/evidence`,
      "POST",
      data,
      "Upload accepted",
    );
    if (result) {
      setUploadResult(result);
      form.reset();
    }
  }

  return (
    <div className="content-stack">
      <PanelHeader
        title="Evidence"
        description="Immutable, content-addressed records captured inside this case."
      />
      {writable(user, caseData) ? (
        <form className="panel-card" onSubmit={(event) => void upload(event)}>
          <h2 className="flex items-center gap-2">
            <Upload size={17} />
            Add evidence
          </h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field
              label="Files"
              hint="Select one or more files. Each is hashed before processing."
            >
              <input required multiple type="file" name="files" />
            </Field>
            <Field label="Source class">
              <select
                name="source_class"
                defaultValue={
                  caseData.demo && allowedSources.includes("SYNTHETIC")
                    ? "SYNTHETIC"
                    : (allowedSources[0] ?? "UPLOAD")
                }
              >
                {allowedSources.map((item) => (
                  <option key={item} value={item}>
                    {humanize(item)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Custody note">
              <input name="note" placeholder="How this material was received" />
            </Field>
            {caseData.demo ? (
              <Field
                label="Synthetic source family"
                hint="Demo cases only; format SYNTHETIC_NAME."
              >
                <input
                  name="source_family"
                  pattern="SYNTHETIC_[A-Z0-9_]{1,80}"
                  placeholder="SYNTHETIC_CHAT"
                />
              </Field>
            ) : null}
          </div>
          <Button className="mt-4" type="submit" disabled={action.busy}>
            <Upload size={15} />
            {action.busy ? "Uploading…" : "Upload evidence"}
          </Button>
          <FormFeedback
            busy={action.busy}
            error={action.error}
            message={action.message}
          />
          {uploadResult ? (
            <div className="mt-4 text-sm">
              <p>
                {uploadResult.results.length} accepted;{" "}
                {uploadResult.errors.length} rejected.
              </p>
              {uploadResult.errors.map((item) => (
                <p className="text-red-400" key={item.filename}>
                  {item.filename}: {item.error.message}
                </p>
              ))}
            </div>
          ) : null}
        </form>
      ) : null}
      <section className="panel-card">
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="Filename">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter by filename"
            />
          </Field>
          <Field label="Status">
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All statuses</option>
              {[
                "PROCESSING",
                "READY",
                "PARTIAL",
                "QUARANTINED",
                "FAILED",
                "EXPIRED",
              ].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </Field>
          <Field label="Source">
            <select
              value={sourceClass}
              onChange={(event) => setSourceClass(event.target.value)}
            >
              <option value="">All sources</option>
              {SOURCE_CLASSES.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </Field>
        </div>
        <ErrorBanner
          error={evidence.error}
          retry={() => void evidence.refetch()}
        />
        {evidence.isLoading ? (
          <Loading label="Loading evidence" />
        ) : evidence.items.length ? (
          <div className="table-wrap mt-5">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Evidence</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Captured</th>
                  <th>Size</th>
                </tr>
              </thead>
              <tbody>
                {evidence.items.map((item) => (
                  <tr
                    key={item.id}
                    className="cursor-pointer"
                    onClick={() => onEvidence(item.id)}
                  >
                    <td>
                      <button className="text-left">
                        <strong>{item.code}</strong>
                        <span className="muted mt-1 block max-w-md truncate text-xs">
                          {item.original_filename}
                        </span>
                      </button>
                    </td>
                    <td>{humanize(item.source_class)}</td>
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                    <td>{date(item.captured_at)}</td>
                    <td>{item.size_bytes.toLocaleString()} B</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No evidence found"
            description="Adjust the filters or add authorised material to this case."
            icon={<Files size={23} />}
          />
        )}
        <LoadMore {...evidence} />
      </section>
    </div>
  );
}

export function SearchView({ caseData, onEvidence }: ViewProps) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<S<"SearchQuery">["mode"]>("hybrid");
  const [sources, setSources] = useState<S<"SearchFilters">["source_class"]>(
    [],
  );
  const [result, setResult] = useState<S<"SearchResult"> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function search(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(
        await api<S<"SearchResult">>(`/cases/${caseData.id}/search`, "POST", {
          query,
          mode,
          k: 20,
          filters: {
            source_class: sources,
            evidence_ids: [],
            lang: [],
            include_quarantined: false,
          },
        } satisfies S<"SearchQuery">),
      );
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  function toggleSource(
    source: NonNullable<S<"SearchFilters">["source_class"]>[number],
  ) {
    setSources((current = []) =>
      current.includes(source)
        ? current.filter((item) => item !== source)
        : [...current, source],
    );
  }

  return (
    <div className="content-stack">
      <PanelHeader
        title="Evidence search"
        description="Hybrid retrieval over captured case material. Results always point back to evidence spans."
      />
      <form className="panel-card" onSubmit={(event) => void search(event)}>
        <div className="grid gap-4 md:grid-cols-[1fr_180px_auto]">
          <Field label="Query">
            <input
              required
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Wallet, alias, phrase, or question"
            />
          </Field>
          <Field label="Retrieval mode">
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value as typeof mode)}
            >
              <option value="hybrid">Hybrid</option>
              <option value="lexical">Lexical</option>
              <option value="semantic">Semantic</option>
            </select>
          </Field>
          <Button className="self-end" type="submit" disabled={busy}>
            <Search size={15} />
            {busy ? "Searching…" : "Search"}
          </Button>
        </div>
        <fieldset className="mt-4">
          <legend className="mb-2 text-sm font-medium">Source classes</legend>
          <div className="flex flex-wrap gap-3">
            {SOURCE_CLASSES.map((source) => (
              <label className="flex items-center gap-2 text-sm" key={source}>
                <input
                  type="checkbox"
                  checked={sources?.includes(source) ?? false}
                  onChange={() => toggleSource(source)}
                />
                {humanize(source)}
              </label>
            ))}
          </div>
        </fieldset>
      </form>
      <ErrorBanner error={error} />
      {result ? (
        <section className="content-stack">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <BadgeLike text={`${result.hits.length} results`} />
            <BadgeLike text={`${humanize(result.mode_used)} used`} />
            {mode !== result.mode_used ? (
              <span className="text-amber-300">
                Requested {mode}; backend returned {result.mode_used}.
              </span>
            ) : null}
            {!result.dense_available ? (
              <span className="muted">
                Dense retrieval unavailable; results reflect the reported
                fallback.
              </span>
            ) : null}
          </div>
          {result.expansions.length ? (
            <p className="muted text-sm">
              Query expansions: {result.expansions.join(", ")}
            </p>
          ) : null}
          {result.hits.length ? (
            result.hits.map((hit) => (
              <article className="panel-card" key={hit.chunk_id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <EvidenceChip
                    code={hit.evidence.code}
                    onClick={() => onEvidence(hit.evidence.id)}
                  />
                  <span className="muted text-xs">
                    {humanize(hit.source_class)} · score {hit.score.toFixed(3)}
                  </span>
                </div>
                <p className="mt-4 whitespace-pre-wrap text-sm leading-7">
                  {hit.snippet}
                </p>
                <div className="muted mt-3 flex flex-wrap gap-2 text-xs">
                  <span>{hit.kind}</span>
                  <span>{hit.lang}</span>
                  {hit.matched_terms.map((term) => (
                    <span key={term}>“{term}”</span>
                  ))}
                </div>
              </article>
            ))
          ) : (
            <EmptyState
              title="No matching passages"
              description="The search completed without evidence-backed hits."
              icon={<FileSearch size={23} />}
            />
          )}
        </section>
      ) : (
        <EmptyState
          title="Search the case record"
          description="Choose a retrieval mode and optional source filters. Quarantined evidence is excluded."
          icon={<Search size={23} />}
        />
      )}
    </div>
  );
}

function BadgeLike({ text }: { text: string }) {
  return (
    <span className="rounded-full border border-border px-2.5 py-1 text-xs">
      {text}
    </span>
  );
}

export function EntitiesView({ caseData, onEvidence }: ViewProps) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const path = useMemo(() => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (type) params.set("type", type);
    return `/cases/${caseData.id}/entities${params.size ? `?${params}` : ""}`;
  }, [caseData.id, query, type]);
  const entities = usePaged<S<"Entity">>(path);
  return (
    <div className="content-stack">
      <PanelHeader
        title="Entities"
        description="Canonical entities derived deterministically from current observations."
      />
      <section className="panel-card">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Entity value">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter canonical value"
            />
          </Field>
          <Field label="Observation type">
            <input
              value={type}
              onChange={(event) => setType(event.target.value.toUpperCase())}
              placeholder="e.g. VENDOR_ALIAS"
            />
          </Field>
        </div>
        <ErrorBanner
          error={entities.error}
          retry={() => void entities.refetch()}
        />
        {entities.isLoading ? (
          <Loading label="Loading entities" />
        ) : entities.items.length ? (
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            {entities.items.map((entity) => (
              <article
                className="rounded-xl border border-border p-4"
                key={entity.id}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <span className="muted text-xs uppercase tracking-wide">
                      {humanize(entity.type)}
                    </span>
                    <h2 className="mt-1 text-base">{entity.display}</h2>
                  </div>
                  <strong>{entity.observation_count}</strong>
                </div>
                <p className="muted mt-2 text-xs">
                  Seen {date(entity.first_seen_at)} –{" "}
                  {date(entity.last_seen_at)}
                </p>
                {entity.sample_spans.length ? (
                  <div className="mt-4 space-y-3">
                    {entity.sample_spans.map((sample, index) => (
                      <div key={`${sample.evidence.id}-${index}`}>
                        <EvidenceChip
                          code={sample.evidence.code}
                          onClick={() => onEvidence(sample.evidence.id)}
                        />
                        <p className="mt-2 line-clamp-2 text-sm">
                          {sample.snippet}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No entities found"
            description="Run extraction on ready evidence or change the filters."
            icon={<UsersRound size={23} />}
          />
        )}
        <LoadMore {...entities} />
      </section>
    </div>
  );
}
