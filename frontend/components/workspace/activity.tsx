"use client";
import { useMemo, useState } from "react";
import { Handle, Position, Controls, type NodeProps } from "@xyflow/react";
import {
  Bot,
  Wrench,
  GitBranch,
  List,
  TerminalSquare,
  X,
  Activity,
  ChevronDown,
  Clock,
} from "lucide-react";
import { Canvas } from "@/components/ai-elements/canvas";
import {
  Agent,
  AgentHeader,
  AgentContent,
} from "@/components/ai-elements/agent";
import {
  Tool,
  ToolHeader,
  ToolContent,
  type ToolPart,
} from "@/components/ai-elements/tool";
import {
  Reasoning,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning";
import { CollapsibleContent } from "@/components/ui/collapsible";
import {
  Terminal,
  TerminalHeader,
  TerminalTitle,
  TerminalActions,
  TerminalCopyButton,
  TerminalContent,
} from "@/components/ai-elements/terminal";
import {
  Button,
  ErrorBanner,
  StatusBadge,
  EvidenceChip,
  money,
} from "./shared";
import type { useRun } from "@/lib/use-run";
import type { S } from "@/lib/types";

type Node = S<"ActivityNode">;
const states: Record<Node["status"], ToolPart["state"]> = {
  queued: "input-streaming",
  running: "input-available",
  completed: "output-available",
  denied: "output-denied",
  failed: "output-error",
  cancelled: "output-error",
  interrupted: "output-error",
};
function ExecutionNode({ data }: NodeProps) {
  const item = data.item as Node;
  const Icon =
    item.kind === "agent" ? Bot : item.kind === "tool" ? Wrench : Activity;
  return (
    <div className="graph-node">
      <Handle type="target" position={Position.Top} />
      <div className="graph-node-label">
        <Icon size={15} />
        {item.display_name || item.label}
      </div>
      <small>{item.agent_role || item.tool_name || item.phase}</small>
      <StatusBadge status={item.status} />
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
const nodeTypes = { execution: ExecutionNode };
export function ActivityPanel({
  run,
  onClose,
  onEvidence,
}: {
  run: ReturnType<typeof useRun>;
  onClose: () => void;
  onEvidence: (id: string) => void;
}) {
  const [tab, setTab] = useState("graph"),
    [selected, setSelected] = useState<string>();
  const snapshot = run.snapshot;
  const graph = useMemo(() => {
    const items = snapshot?.nodes ?? [],
      ids = new Set(items.map((n) => n.id)),
      depths = new Map<string, number>(),
      rows = new Map<number, number>();
    function depth(n: Node, seen = new Set<string>()): number {
      if (depths.has(n.id)) return depths.get(n.id)!;
      if (seen.has(n.id)) return 0;
      seen.add(n.id);
      const parent = items.find((p) => p.id === n.parent_id);
      const d = parent ? Math.min(depth(parent, seen) + 1, 20) : 0;
      depths.set(n.id, d);
      return d;
    }
    const nodes = items.map((n) => {
      const d = depth(n),
        col = rows.get(d) ?? 0;
      rows.set(d, col + 1);
      return {
        id: n.id,
        type: "execution",
        data: { item: n },
        position: { x: col * 255, y: d * 155 },
        selectable: true,
      };
    });
    return {
      nodes,
      edges: (snapshot?.edges ?? [])
        .filter((e) => ids.has(e.source) && ids.has(e.target))
        .map((e) => ({
          ...e,
          id: e.source + e.target,
          type: "smoothstep",
          style: { stroke: "var(--primary)", strokeWidth: 1 },
          animated: false,
        })),
    };
  }, [snapshot?.nodes, snapshot?.edges]);
  const node = snapshot?.nodes.find((n) => n.id === selected);
  const output = (snapshot?.events ?? [])
    .map(
      (e) =>
        `${e.seq.toString().padStart(3, "0")}  [${e.status.toUpperCase()}] ${e.display_name || e.label}${e.transport ? ` (${e.transport})` : ""}\n     ${e.summary}${e.error_code ? ` · ${e.error_code}` : ""}`,
    )
    .join("\n\n");
  const renderDetail = (n: Node) => (
    <div className="space-y-3 text-xs">
      <div className="flex flex-wrap gap-2">
        <StatusBadge status={n.status} />
        {n.transport && <span className="status-pill">{n.transport}</span>}
        {n.cached && <span className="status-pill">Cached</span>}
      </div>
      <p className="muted leading-relaxed">
        {n.summary || "Waiting for a progress update."}
      </p>
      <dl className="grid grid-cols-2 gap-2 text-[10px] text-muted-foreground">
        <dt>Phase</dt>
        <dd>{n.phase}</dd>
        {n.integration_id && (
          <>
            <dt>Integration</dt>
            <dd>{n.integration_id}</dd>
          </>
        )}
        {n.duration_ms != null && (
          <>
            <dt>Duration</dt>
            <dd>{(n.duration_ms / 1000).toFixed(2)}s</dd>
          </>
        )}
        {n.error_code && (
          <>
            <dt>Error</dt>
            <dd>{n.error_code}</dd>
          </>
        )}
      </dl>
      <div className="flex flex-wrap gap-1">
        {(n.evidence_codes ?? []).map((code, i) => (
          <EvidenceChip
            key={code}
            code={code}
            onClick={() => onEvidence(n.evidence_ids?.[i] ?? code)}
          />
        ))}
      </div>
      {n.terminal_inferred && (
        <p className="text-[10px] text-muted-foreground">
          Final status inferred from the run ending.
        </p>
      )}
    </div>
  );
  return (
    <aside className="activity-sidebar" aria-label="Agent activity">
      <div className="activity-heading">
        <div className="flex items-center gap-2">
          <GitBranch size={16} />
          <strong className="font-medium">Agent activity</strong>
        </div>
        <Button
          size="icon-sm"
          variant="ghost"
          onClick={onClose}
          aria-label="Close activity"
        >
          <X />
        </Button>
      </div>
      <div className="activity-tabs" role="tablist" aria-label="Activity view">
        {[
          ["graph", "Graph", GitBranch],
          ["timeline", "Timeline", List],
          ["console", "Output", TerminalSquare],
        ].map(([id, label, Icon]) => {
          const I = Icon as typeof GitBranch;
          return (
            <button
              role="tab"
              aria-selected={tab === id}
              className={tab === id ? "active" : ""}
              key={String(id)}
              onClick={() => setTab(String(id))}
            >
              <I size={13} />
              {String(label)}
            </button>
          );
        })}
      </div>
      <div className="activity-body">
        <ErrorBanner error={run.error || run.streamError} />
        {!snapshot?.nodes.length ? (
          <div className="graph-empty">
            <div>
              <GitBranch size={34} />
              <p className="text-xs">
                {run.active
                  ? "Waiting for recorded activity…"
                  : "Your investigation, in motion"}
              </p>
              <p className="text-[10px] leading-relaxed mt-2">
                Agents, tools, and connections appear here as a case run uses
                them.
              </p>
            </div>
          </div>
        ) : (
          <>
            {tab === "graph" && (
              <div className="space-y-4">
                <div className="graph-stage">
                  <Canvas
                    nodes={graph.nodes}
                    edges={graph.edges}
                    nodeTypes={nodeTypes}
                    deleteKeyCode={null}
                    nodesDraggable={false}
                    nodesConnectable={false}
                    edgesReconnectable={false}
                    selectionOnDrag={false}
                    panOnDrag
                    fitView
                    minZoom={0.15}
                    maxZoom={1.6}
                    onNodeClick={(_, n) => setSelected(n.id)}
                  >
                    <Controls showInteractive={false} />
                  </Canvas>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  Select a node to inspect its progress and evidence.
                </p>
                {node && (
                  <div className="panel-card !p-4">
                    <h3 className="text-xs font-medium mb-3">
                      {node.display_name || node.label}
                    </h3>
                    {renderDetail(node)}
                  </div>
                )}
                {snapshot.nodes
                  .filter((n) => n.kind === "agent")
                  .map((n) => (
                    <Agent key={n.id}>
                      <AgentHeader
                        name={n.display_name || n.label}
                        model={n.agent_role || undefined}
                      />
                      <AgentContent>{renderDetail(n)}</AgentContent>
                    </Agent>
                  ))}
                {snapshot.nodes
                  .filter((n) => n.kind === "tool")
                  .map((n) => (
                    <Tool key={n.id}>
                      <ToolHeader
                        type="dynamic-tool"
                        toolName={n.tool_name || n.label}
                        title={n.display_name || n.label}
                        state={states[n.status]}
                      />
                      <ToolContent>{renderDetail(n)}</ToolContent>
                    </Tool>
                  ))}
                {snapshot.nodes.some((n) => n.kind === "stage") && (
                  <Reasoning defaultOpen={false}>
                    <ReasoningTrigger>
                      <Activity size={14} />
                      <span>Public progress summaries</span>
                      <ChevronDown size={13} />
                    </ReasoningTrigger>
                    <CollapsibleContent className="space-y-3 pt-3">
                      {snapshot.nodes
                        .filter((n) => n.kind === "stage")
                        .map((n) => (
                          <div key={n.id}>
                            <h4 className="text-xs mb-2">{n.label}</h4>
                            {renderDetail(n)}
                          </div>
                        ))}
                    </CollapsibleContent>
                  </Reasoning>
                )}
              </div>
            )}
            {tab === "timeline" && (
              <div>
                {snapshot.events.map((e) => (
                  <div className="timeline-item" key={`${e.id}-${e.seq}`}>
                    <div className="timeline-dot">
                      <Clock size={12} />
                    </div>
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <strong>{e.display_name || e.label}</strong>
                        <StatusBadge status={e.status} />
                      </div>
                      <p>{e.summary}</p>
                      <small>
                        #{e.seq}
                        {e.transport ? ` · ${e.transport}` : ""}
                        {e.duration_ms != null
                          ? ` · ${(e.duration_ms / 1000).toFixed(2)}s`
                          : ""}
                      </small>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {tab === "console" && (
              <>
                <p className="text-[10px] text-muted-foreground mb-3">
                  Recorded activity output
                </p>
                <Terminal output={output} isStreaming={run.active}>
                  <TerminalHeader>
                    <TerminalTitle>Run log</TerminalTitle>
                    <TerminalActions>
                      <TerminalCopyButton />
                    </TerminalActions>
                  </TerminalHeader>
                  <TerminalContent className="text-[10px] max-h-none" />
                </Terminal>
              </>
            )}
            {snapshot.truncated && (
              <p className="draft-label mt-4">
                Showing the latest 10,000 activity events.
              </p>
            )}
          </>
        )}
      </div>
      <footer className="activity-footer">
        <span className="flex items-center gap-2">
          <i className="live-dot" />
          {run.info?.status ?? "No run selected"}
        </span>
        <span>
          {run.connection === "reconnecting"
            ? "Reconnecting…"
            : run.info
              ? `${money(run.info.cost_usd)}${(snapshot?.cost_complete ?? run.info.cost_complete) === false ? " · partial" : (snapshot?.cost_complete ?? run.info.cost_complete) == null ? " · completeness unknown" : ""}`
              : "Ready when you are"}
        </span>
      </footer>
    </aside>
  );
}
