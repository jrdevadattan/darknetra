"use client";

import { useMemo, useState, type FormEvent } from "react";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  GitBranch,
  Link2,
  Plus,
  Scale,
  Sparkles,
  UsersRound,
} from "lucide-react";
import { writable } from "@/lib/permissions";
import { useApi, usePaged } from "@/lib/api";
import type { S } from "@/lib/types";
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
import { FormFeedback, humanize, useCaseAction } from "./case-forms";

type ViewProps = {
  caseData: S<"Case">;
  user: S<"UserMe">;
  onEvidence: (id: string) => void;
};

export function RelationshipsView({ caseData, onEvidence }: ViewProps) {
  const graph = useApi<S<"GraphDTO">>(
    `/cases/${caseData.id}/graph?depth=2&include_pending=true&include_rejected=false`,
  );
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<S<"GraphNode"> | null>(null);
  const provenance = useApi<S<"EdgeProvenance">>(
    selectedEdge
      ? `/cases/${caseData.id}/graph/edges/${selectedEdge}/provenance`
      : null,
  );
  const nodes = useMemo<Node[]>(
    () =>
      (graph.data?.nodes ?? []).map((node, index) => ({
        id: node.id,
        position: { x: (index % 5) * 230, y: Math.floor(index / 5) * 145 },
        data: { label: `${node.label}\n${humanize(node.type)}` },
        style: {
          width: 180,
          border:
            "1px solid color-mix(in srgb, var(--border) 85%, transparent)",
          borderRadius: 12,
          background: "var(--card)",
          color: "var(--foreground)",
          fontSize: 12,
          whiteSpace: "pre-line",
          padding: 12,
        },
      })),
    [graph.data?.nodes],
  );
  const edges = useMemo<Edge[]>(
    () =>
      (graph.data?.edges ?? []).map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: humanize(edge.type),
        markerEnd: { type: MarkerType.ArrowClosed },
        style: {
          stroke:
            edge.status === "CONFIRMED"
              ? "#34d399"
              : edge.status === "REJECTED"
                ? "#f87171"
                : "#94a3b8",
        },
        labelStyle: { fill: "var(--muted-foreground)", fontSize: 10 },
      })),
    [graph.data?.edges],
  );

  return (
    <div className="content-stack">
      <PanelHeader
        title="Relationships"
        description="Read-only graph of persisted nodes and materialised edges. Select an edge for provenance."
      >
        {graph.data?.truncated ? (
          <span className="text-sm text-amber-300">
            Graph truncated by API bounds
          </span>
        ) : null}
      </PanelHeader>
      <ErrorBanner error={graph.error} retry={() => void graph.refetch()} />
      {graph.isLoading ? (
        <Loading label="Loading relationship graph" />
      ) : graph.data?.nodes.length ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
          <section className="panel-card h-[620px] overflow-hidden p-0">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              fitView
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              onNodeClick={(_, node) =>
                setSelectedNode(
                  graph.data?.nodes.find((item) => item.id === node.id) ?? null,
                )
              }
              onEdgeClick={(_, edge) => setSelectedEdge(edge.id)}
            >
              <Background gap={24} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </section>
          <aside className="panel-card self-start">
            {selectedEdge ? (
              <>
                <h2>Edge provenance</h2>
                {provenance.isLoading ? (
                  <Loading label="Loading provenance" />
                ) : null}
                <ErrorBanner error={provenance.error} />
                {provenance.data ? (
                  <div className="mt-4 content-stack">
                    <div>
                      <StatusBadge status={provenance.data.edge.status} />
                      <p className="mt-2 text-sm">
                        {humanize(provenance.data.edge.type)}
                        {provenance.data.edge.score != null
                          ? ` · score ${provenance.data.edge.score.toFixed(1)}`
                          : ""}
                      </p>
                    </div>
                    {provenance.data.edge.families.length ? (
                      <p className="muted text-sm">
                        Independent families:{" "}
                        {provenance.data.edge.families.join(", ")}
                      </p>
                    ) : null}
                    <div>
                      <h3 className="text-sm font-medium">
                        Supporting evidence
                      </h3>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {provenance.data.evidence.map((item) => (
                          <EvidenceChip
                            key={item.id}
                            code={item.code}
                            onClick={() => onEvidence(item.id)}
                          />
                        ))}
                      </div>
                    </div>
                    {provenance.data.candidate ? (
                      <div>
                        <h3 className="text-sm font-medium">Candidate</h3>
                        <p className="muted mt-1 text-sm">
                          {provenance.data.candidate.subject_a.display} ↔{" "}
                          {provenance.data.candidate.subject_b.display} ·{" "}
                          {provenance.data.candidate.band}
                        </p>
                      </div>
                    ) : null}
                    {provenance.data.decision ? (
                      <div>
                        <h3 className="text-sm font-medium">Human decision</h3>
                        <p className="mt-1 text-sm">
                          {humanize(provenance.data.decision.decision)} ·{" "}
                          {provenance.data.decision.decided_by.display}
                        </p>
                        <p className="muted mt-1 text-sm">
                          {provenance.data.decision.rationale}
                        </p>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </>
            ) : selectedNode ? (
              <>
                <h2>Node details</h2>
                <div className="mt-4 space-y-3">
                  <StatusBadge status={selectedNode.status} />
                  <h3>{selectedNode.label}</h3>
                  <p className="muted text-sm">
                    {humanize(selectedNode.type)} · degree {selectedNode.degree}
                  </p>
                </div>
              </>
            ) : (
              <EmptyState
                title="Inspect the graph"
                description="Select a node for its stored status or an edge for its evidence and decision trail."
                icon={<GitBranch size={23} />}
              />
            )}
          </aside>
        </div>
      ) : (
        <EmptyState
          title="No relationships yet"
          description="The graph will populate after extraction and correlation create persisted edges."
          icon={<GitBranch size={23} />}
        />
      )}
    </div>
  );
}

type CandidateTarget = {
  type: "LINK" | "ACTIVITY";
  id: string;
  label: string;
  version?: number;
};

export function FindingsView({ caseData, user, onEvidence }: ViewProps) {
  const findings = usePaged<S<"Finding">>(`/cases/${caseData.id}/findings`);
  const evidence = usePaged<S<"Evidence">>(
    `/cases/${caseData.id}/evidence?status=READY`,
  );
  const links = usePaged<S<"LinkCandidate">>(
    `/cases/${caseData.id}/analytics/links`,
  );
  const activity = usePaged<S<"ActivityCandidate">>(
    `/cases/${caseData.id}/analytics/activity`,
  );
  const decisions = usePaged<S<"Decision">>(`/cases/${caseData.id}/decisions`);
  const action = useCaseAction(caseData.id);
  const [createOpen, setCreateOpen] = useState(false);
  const [promote, setPromote] = useState<S<"Finding"> | null>(null);
  const [candidate, setCandidate] = useState<CandidateTarget | null>(null);

  async function createFinding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const evidenceCodes = data.getAll("evidence_codes").map(String);
    if (!evidenceCodes.length) {
      action.fail(new Error("Select at least one supporting evidence record."));
      return;
    }
    const result = await action.run<S<"Finding">>(
      `/cases/${caseData.id}/findings`,
      "POST",
      {
        title: String(data.get("title")),
        claim: String(data.get("claim")),
        evidence_codes: evidenceCodes,
        method: "analyst_manual",
        method_version: "1",
        kind_hint: String(data.get("kind_hint") || "OBSERVED"),
      } satisfies S<"FindingCreate">,
      "Draft finding created",
    );
    if (result) {
      setCreateOpen(false);
      form.reset();
    }
  }

  async function promoteFinding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!promote) return;
    const rationale = String(
      new FormData(event.currentTarget).get("rationale"),
    );
    const result = await action.run<S<"Finding">>(
      `/cases/${caseData.id}/findings/${promote.id}/promote`,
      "POST",
      {
        target_type: "FINDING",
        target_id: promote.id,
        decision: "ACCEPT",
        rationale,
        supersede: false,
      } satisfies S<"DecisionCreate">,
      "Finding promoted with human decision",
    );
    if (result) setPromote(null);
  }

  async function decideCandidate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!candidate) return;
    const data = new FormData(event.currentTarget);
    const result = await action.run<S<"Decision">>(
      `/cases/${caseData.id}/decisions`,
      "POST",
      {
        target_type: candidate.type,
        target_id: candidate.id,
        decision: String(
          data.get("decision"),
        ) as S<"DecisionCreate">["decision"],
        rationale: String(data.get("rationale")),
        supersede: false,
      } satisfies S<"DecisionCreate">,
      "Decision recorded",
    );
    if (result) setCandidate(null);
  }

  return (
    <div className="content-stack">
      <PanelHeader
        title="Findings & decisions"
        description="Draft claims remain separate from human-confirmed findings and scored candidates."
      >
        {writable(user, caseData) ? (
          <Button
            onClick={() => {
              action.clear();
              setCreateOpen(true);
            }}
          >
            <Plus size={15} />
            New finding
          </Button>
        ) : null}
      </PanelHeader>
      <section className="panel-card">
        <h2>Findings</h2>
        <ErrorBanner
          error={findings.error}
          retry={() => void findings.refetch()}
        />
        {findings.isLoading ? (
          <Loading label="Loading findings" />
        ) : findings.items.length ? (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {findings.items.map((finding) => (
              <article
                className="rounded-xl border border-border p-4"
                key={finding.id}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex gap-2">
                    <StatusBadge status={finding.status} />
                    <span className="muted text-xs">
                      {finding.kind} · v{finding.version}
                    </span>
                  </div>
                  <span className="muted text-xs">{date(finding.at)}</span>
                </div>
                <h3 className="mt-3 text-base">{finding.title}</h3>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6">
                  {finding.claim}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {finding.evidence.map((item) => (
                    <EvidenceChip
                      key={item.id}
                      code={item.code}
                      onClick={() => onEvidence(item.id)}
                    />
                  ))}
                </div>
                {finding.decision ? (
                  <p className="muted mt-3 text-xs">
                    {finding.decision.decided_by.display}:{" "}
                    {finding.decision.rationale}
                  </p>
                ) : null}
                {finding.status === "DRAFT" && writable(user, caseData) ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-4"
                    onClick={() => {
                      action.clear();
                      setPromote(finding);
                    }}
                  >
                    <Scale size={14} />
                    Promote
                  </Button>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            title="No findings"
            description="Create a cited draft from evidence or escalate an alert."
            icon={<Sparkles size={23} />}
          />
        )}
        <LoadMore {...findings} />
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="panel-card">
          <h2 className="flex items-center gap-2">
            <Link2 size={17} />
            Link candidates
          </h2>
          <ErrorBanner error={links.error} />
          {links.items.length ? (
            <div className="mt-4 space-y-3">
              {links.items.map((item) => (
                <article
                  className="rounded-xl border border-border p-4"
                  key={item.id}
                >
                  <div className="flex justify-between gap-3">
                    <div>
                      <h3 className="text-sm">
                        {item.subject_a.display} ↔ {item.subject_b.display}
                      </h3>
                      <p className="muted mt-1 text-xs">
                        {item.families.join(", ") ||
                          "No independent families reported"}
                      </p>
                    </div>
                    <div className="text-right">
                      <strong>{item.score}</strong>
                      <StatusBadge status={item.status} />
                    </div>
                  </div>
                  {item.rescored ? (
                    <p className="mt-2 text-xs text-amber-300">
                      Re-scored as version {item.version}; prior decisions
                      remain preserved.
                    </p>
                  ) : null}
                  {!item.decision && writable(user, caseData) ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-3"
                      onClick={() => {
                        action.clear();
                        setCandidate({
                          type: "LINK",
                          id: item.id,
                          label: `${item.subject_a.display} ↔ ${item.subject_b.display}`,
                          version: item.version,
                        });
                      }}
                    >
                      Decide
                    </Button>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <p className="muted mt-4 text-sm">No link candidates returned.</p>
          )}
          <LoadMore {...links} />
        </section>
        <section className="panel-card">
          <h2 className="flex items-center gap-2">
            <UsersRound size={17} />
            Activity candidates
          </h2>
          <ErrorBanner error={activity.error} />
          {activity.items.length ? (
            <div className="mt-4 space-y-3">
              {activity.items.map((item) => (
                <article
                  className="rounded-xl border border-border p-4"
                  key={item.id}
                >
                  <div className="flex justify-between gap-3">
                    <div>
                      <h3 className="text-sm">{humanize(item.label)}</h3>
                      <EvidenceChip
                        code={item.evidence.code}
                        onClick={() => onEvidence(item.evidence.id)}
                      />
                    </div>
                    <div className="text-right">
                      <strong>{item.score.toFixed(2)}</strong>
                      <StatusBadge status={item.status} />
                    </div>
                  </div>
                  {item.status === "PENDING" && writable(user, caseData) ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-3"
                      onClick={() => {
                        action.clear();
                        setCandidate({
                          type: "ACTIVITY",
                          id: item.id,
                          label: item.label,
                        });
                      }}
                    >
                      Decide
                    </Button>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <p className="muted mt-4 text-sm">
              No activity candidates returned.
            </p>
          )}
          <LoadMore {...activity} />
        </section>
      </div>
      <section className="panel-card">
        <h2>Decision ledger</h2>
        {decisions.items.length ? (
          <div className="table-wrap mt-4">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Target</th>
                  <th>Decision</th>
                  <th>Analyst</th>
                  <th>Rationale</th>
                  <th>At</th>
                </tr>
              </thead>
              <tbody>
                {decisions.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.target_type}</td>
                    <td>{humanize(item.decision)}</td>
                    <td>{item.decided_by.display}</td>
                    <td className="max-w-md">{item.rationale}</td>
                    <td>{date(item.at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted mt-3 text-sm">No human decisions recorded.</p>
        )}
        <LoadMore {...decisions} />
      </section>

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create draft finding"
        description="Every claim needs one or more evidence codes."
      >
        <form
          onSubmit={(event) => void createFinding(event)}
          className="content-stack"
        >
          <Field label="Title">
            <input required name="title" maxLength={300} />
          </Field>
          <Field label="Claim">
            <textarea required name="claim" rows={5} />
          </Field>
          <Field label="Kind">
            <select name="kind_hint">
              <option>OBSERVED</option>
              <option>MODEL</option>
              <option>CANDIDATE</option>
            </select>
          </Field>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">
              Supporting evidence
            </legend>
            <div className="max-h-44 space-y-2 overflow-auto rounded-lg border border-border p-3">
              {evidence.items.map((item) => (
                <label
                  className="flex items-center gap-2 text-sm"
                  key={item.id}
                >
                  <input
                    type="checkbox"
                    name="evidence_codes"
                    value={item.code}
                  />
                  <span className="font-mono">{item.code}</span>
                  <span className="muted truncate">
                    {item.original_filename}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <FormFeedback
            busy={action.busy}
            error={action.error}
            message={action.message}
          />
          <Button disabled={action.busy} type="submit">
            Create draft
          </Button>
        </form>
      </Modal>
      <Modal
        open={Boolean(promote)}
        onClose={() => setPromote(null)}
        title="Promote finding"
        description="Promotion records an immutable ACCEPT decision and rationale."
      >
        <form
          onSubmit={(event) => void promoteFinding(event)}
          className="content-stack"
        >
          <p className="text-sm">{promote?.title}</p>
          <Field label="Decision rationale">
            <textarea required name="rationale" rows={5} />
          </Field>
          <FormFeedback busy={action.busy} error={action.error} />
          <Button disabled={action.busy} type="submit">
            Accept and promote
          </Button>
        </form>
      </Modal>
      <Modal
        open={Boolean(candidate)}
        onClose={() => setCandidate(null)}
        title="Decide candidate"
        description={candidate?.label}
      >
        <form
          onSubmit={(event) => void decideCandidate(event)}
          className="content-stack"
        >
          <Field label="Decision">
            <select name="decision">
              <option>ACCEPT</option>
              <option>REJECT</option>
              <option>DEFER</option>
              <option>REQUEST_MORE_EVIDENCE</option>
            </select>
          </Field>
          <Field label="Rationale">
            <textarea required name="rationale" rows={5} />
          </Field>
          <FormFeedback busy={action.busy} error={action.error} />
          <Button disabled={action.busy} type="submit">
            Record decision
          </Button>
        </form>
      </Modal>
    </div>
  );
}
