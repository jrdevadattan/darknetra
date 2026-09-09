"use client";
import { useLanguage } from "./language";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "next-themes";
import {
  Background,
  Controls,
  ReactFlow,
  Position,
  MarkerType,
  MiniMap,
  useNodesInitialized,
  useReactFlow,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  ArrowLeftRight,
  Check,
  ExternalLink,
  GitBranch,
  List,
  LoaderCircle,
  Maximize2,
  Minimize2,
  ShieldCheck,
  FileText,
  FolderOpen,
  Text,
  X,
  Search,
  Focus,
  Scan,
  RotateCcw,
  CircleAlert,
} from "lucide-react";
import { PanelResize } from "./panel-resize";
import { NetraStatus } from "./netra-status";
import { ActivitySteps, SpecialistAgents } from "./agents";
import { InvestigationTimeline } from "./investigation-timeline";
import {
  ActionIcon,
  CaseMarkdown,
  CopyControl,
  FileIcon,
  InvestigatorIcon,
  SiteIcon,
  SourceCard,
} from "./source-ui";
import {
  buildEvidenceGraph,
  graphOverview,
  layoutEvidenceGraph,
} from "@/lib/evidence-graph";
import type { ChatAttachment, ChatMessage } from "@/lib/chat-types";

const statusLabel: Record<string, string> = {
  running: "Working",
  in_progress: "Working",
  done: "Completed",
  completed: "Completed",
  pending: "Starting",
  error: "Failed",
  failed: "Failed",
  stopped: "Stopped",
  unverified: "Unconfirmed",
  retrieved: "Retrieved",
  analysed: "Examined",
  listed: "Unverified reference",
  supplied: "Uploaded",
  referenced: "Referenced · retrieval not recorded",
};
const noFiles: ChatAttachment[] = [];
function GraphViewport({ layoutKey }: { layoutKey: string }) {
  const ready = useNodesInitialized();
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (!ready) return;
    const frame = requestAnimationFrame(
      () => void fitView({ padding: 0.08, minZoom: 0.65, maxZoom: 0.9 }),
    );
    return () => cancelAnimationFrame(frame);
  }, [ready, fitView, layoutKey]);
  return null;
}
function Status({ value }: { value: string }) {
  const { t } = useLanguage();
  return (
    <span className={`agent-status ${value}`}>
      {["running", "in_progress", "pending"].includes(value) ? (
        <LoaderCircle size={12} className="spin" />
      ) : ["done", "completed", "retrieved", "analysed"].includes(value) ? (
        <Check size={12} />
      ) : null}
      {t(statusLabel[value] || value)}
    </span>
  );
}

export function ActivityPanel({
  message,
  files = noFiles,
  chatId,
  onClose,
  onSwap,
  width = 520,
  side = "right",
  onResize,
}: {
  message?: ChatMessage;
  files?: ChatAttachment[];
  chatId?: string;
  onClose: () => void;
  onSwap: () => void;
  width?: number;
  side?: "left" | "right";
  onResize?: (width: number) => void;
}) {
  const { t } = useLanguage();
  const { resolvedTheme } = useTheme();
  const [tab, setTab] = useState("timeline");
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState("");
  const [selectedEdge, setSelectedEdge] = useState("");
  const [graphMode, setGraphMode] = useState<"overview" | "all">("overview");
  const [query, setQuery] = useState("");
  const [zoom, setZoom] = useState(100);
  const [canvas, setCanvas] = useState<HTMLDivElement | null>(null);
  const [columns, setColumns] = useState(2);
  useEffect(() => {
    if (!canvas) return;
    const observer = new ResizeObserver(([entry]) =>
      setColumns(
        entry.contentRect.width >= 1000
          ? 4
          : entry.contentRect.width >= 740
            ? 3
            : 2,
      ),
    );
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [canvas]);
  const flow = useRef<
    | (Pick<ReactFlowInstance, "setCenter"> & {
        fitView: (options: {
          padding?: number;
          duration?: number;
          minZoom?: number;
          maxZoom?: number;
        }) => Promise<boolean>;
      })
    | null
  >(null);
  const fullGraph = useMemo(
    () => (message ? buildEvidenceGraph(message, files) : undefined),
    [message, files],
  );
  const graph = useMemo(
    () =>
      fullGraph
        ? layoutEvidenceGraph(
            graphMode === "overview" ? graphOverview(fullGraph) : fullGraph,
            columns,
          )
        : undefined,
    [fullGraph, graphMode, columns],
  );
  function inspectSource(id: string) {
    setSelected(id);
    setSelectedEdge("");
    setTab("graph");
  }
  function focusNode(id: string) {
    inspectSource(id);
    const node = graph?.nodes.find((n) => n.id === id);
    if (node)
      void flow.current?.setCenter(node.x + 110, node.y + 55, {
        zoom: 1,
        duration: 220,
      });
  }
  const focused =
    graph?.nodes.find((n) => n.id === selected) ||
    graph?.nodes.find((n) => n.kind === "source") ||
    graph?.nodes[0];
  const connection = graph?.edges.find((e) => e.id === selectedEdge);
  const matches = query.trim()
    ? graph?.nodes
        .filter((n) =>
          `${n.title} ${n.source?.url || ""}`
            .toLowerCase()
            .includes(query.trim().toLowerCase()),
        )
        .slice(0, 12) || []
    : [];
  const connected = new Set(
    graph?.edges
      .filter((e) => e.source === selected || e.target === selected)
      .flatMap((e) => [e.source, e.target]) || [],
  );
  const sourceOptions = { chatId, files, onInspectSource: inspectSource };
  const sources =
    graph?.nodes.flatMap((n) => (n.source ? [n.source] : [])) || [];
  useEffect(() => {
    setTab(message?.status === "done" ? "graph" : "timeline");
  }, [message?.id, message?.status]);
  useEffect(() => {
    setSelected("");
    setSelectedEdge("");
    setQuery("");
    setGraphMode("overview");
  }, [message?.id]);
  const nodes = useMemo(
    () =>
      graph?.nodes.map((node) => ({
        id: node.id,
        position: { x: node.x, y: node.y },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        className: `evidence-node evidence-node-${node.kind} ${focused?.id === node.id ? "evidence-selected" : ""} ${selected && !connected.has(node.id) && selected !== node.id ? "evidence-dimmed" : ""} ${["failed", "error", "unverified"].includes(node.status) ? "evidence-needs-review" : ""}`,
        data: {
          label: (
            <>
              <div className="graph-node-icon">
                {node.source?.url ? (
                  <SiteIcon
                    url={node.source.url}
                    favicon={node.source.favicon}
                    size={20}
                  />
                ) : node.source?.file ? (
                  <FileIcon name={node.title} size={20} />
                ) : node.kind === "lead" || node.kind === "agent" ? (
                  <InvestigatorIcon name={node.title} size={20} />
                ) : node.kind === "report" ? (
                  <FileText size={20} />
                ) : node.kind === "input" ? (
                  <FolderOpen size={20} />
                ) : node.memberIds ? (
                  <CircleAlert size={20} />
                ) : (
                  <ActionIcon label={node.title} size={20} />
                )}
              </div>
              <small>
                {node.kind === "source"
                  ? node.source?.kind === "file"
                    ? "FILE"
                    : "SOURCE"
                  : node.kind.toUpperCase()}
              </small>
              <strong>{node.title}</strong>
              {node.status === "referenced" ? (
                <span className="agent-status">Referenced</span>
              ) : (
                <Status value={node.status} />
              )}
            </>
          ),
        },
        ariaLabel: `${node.title}, ${statusLabel[node.status] || node.status}`,
      })) || [],
    [graph, focused?.id, selected],
  );
  const edges = useMemo(
    () =>
      graph?.edges.map((edge) => ({
        ...edge,
        type: "smoothstep",
        markerEnd: { type: MarkerType.ArrowClosed },
        className: `evidence-edge ${selected && edge.source !== selected && edge.target !== selected ? "evidence-dimmed" : ""}`,
        selected: selectedEdge === edge.id,
        ariaLabel: `${graph.nodes.find((n) => n.id === edge.source)?.title}: ${edge.label} ${graph.nodes.find((n) => n.id === edge.target)?.title}`,
      })) || [],
    [graph, selectedEdge, selected],
  );
  return (
    <aside
      className={`activity-panel investigation-panel ${expanded ? "expanded" : ""} ${tab === "graph" ? "graph-active" : ""}`}
      aria-label={t("Agent activity")}
    >
      {onResize && !expanded && (
        <PanelResize
          label="Resize activity sidebar"
          side={side === "left" ? "right" : "left"}
          width={width}
          onResize={onResize}
          minimum={300}
          maximum={960}
          initial={520}
        />
      )}
      <header className="investigation-header">
        <strong>
          <GitBranch size={17} />
          {t("Agent activity")}
        </strong>
        <div className="panel-actions">
          <button
            className="icon-button swap-panels"
            aria-label="Swap conversation and activity"
            onClick={onSwap}
          >
            <ArrowLeftRight size={15} />
          </button>
          <button
            className="icon-button"
            aria-label={expanded ? "Collapse activity" : "Expand activity"}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
          <button
            className="icon-button"
            aria-label="Close activity"
            onClick={onClose}
          >
            <X size={17} />
          </button>
        </div>
      </header>
      <div
        className="activity-tabs"
        role="tablist"
        aria-label="Investigation views"
      >
        {[
          ["timeline", List, t("Timeline")],
          ["graph", GitBranch, t("Evidence graph")],
          ["output", Text, t("Output")],
        ].map(([id, Icon, label]) => {
          const TabIcon = Icon as typeof List;
          return (
            <button
              key={id as string}
              id={`run-tab-${id}`}
              role="tab"
              aria-selected={tab === id}
              aria-controls={`run-panel-${id}`}
              onClick={() => setTab(id as string)}
            >
              <TabIcon size={14} />
              {label as string}
            </button>
          );
        })}
      </div>
      {!message ? (
        <p className="activity-empty">
          Send a message to start the investigation timeline.
        </p>
      ) : (
        <>
          <button
            type="button"
            className="run-overview"
            aria-label="View lead investigator report"
            onClick={() => setTab("output")}
          >
            <span className="run-lead-icon">
              <ShieldCheck size={21} />
            </span>
            <div>
              <strong>
                {message.netra ? "Netra Case Lead" : t("Lead Investigator")}
              </strong>
              <p>
                {message.status === "running"
                  ? message.agents?.some((a) =>
                      ["pending", "running"].includes(a.status),
                    )
                    ? "Coordinating specialist reviews"
                    : "Reviewing the case"
                  : message.netra && message.netra.status !== "complete"
                    ? "Review has unresolved work"
                    : message.status === "done"
                      ? t("Review complete")
                      : "Review ended before completion"}
              </p>
            </div>
            <Status
              value={
                message.netra &&
                message.status === "done" &&
                message.netra.status !== "complete"
                  ? "unverified"
                  : message.status
              }
            />
          </button>
          {message.netra && <NetraStatus goal={message.netra} />}
          <section
            className="activity-view"
            id={`run-panel-${tab}`}
            role="tabpanel"
            aria-labelledby={`run-tab-${tab}`}
          >
            {tab === "timeline" && (
              <InvestigationTimeline
                key={message.id}
                message={message}
                {...sourceOptions}
              />
            )}
            {tab === "graph" && graph && (
              <>
                <div className="graph-toolbar">
                  <div
                    className="graph-mode"
                    role="group"
                    aria-label="Graph detail"
                  >
                    <button
                      type="button"
                      aria-pressed={graphMode === "overview"}
                      onClick={() => {
                        setGraphMode("overview");
                        setSelected("");
                        setSelectedEdge("");
                      }}
                    >
                      Overview
                    </button>
                    <button
                      type="button"
                      aria-pressed={graphMode === "all"}
                      onClick={() => {
                        setGraphMode("all");
                        setSelected("");
                        setSelectedEdge("");
                      }}
                    >
                      All steps
                    </button>
                  </div>
                  <div className="graph-tools">
                    <button
                      className="icon-button"
                      title="Fit entire graph"
                      aria-label="Fit entire graph"
                      onClick={() =>
                        void flow.current?.fitView({
                          padding: 0.15,
                          duration: 220,
                          minZoom: 0.08,
                          maxZoom: 1,
                        })
                      }
                    >
                      <Scan size={16} />
                    </button>
                    <button
                      className="icon-button"
                      title="Focus selected item"
                      aria-label="Focus selected item"
                      disabled={!focused}
                      onClick={() => focused && focusNode(focused.id)}
                    >
                      <Focus size={16} />
                    </button>
                    <button
                      className="icon-button"
                      title="Reset graph view"
                      aria-label="Reset graph view"
                      onClick={() => {
                        setSelected("");
                        setSelectedEdge("");
                        void flow.current?.fitView({
                          padding: 0.15,
                          duration: 220,
                          minZoom: 0.65,
                          maxZoom: 0.9,
                        });
                      }}
                    >
                      <RotateCcw size={14} />
                    </button>
                  </div>
                </div>
                <div className="graph-search">
                  <Search size={15} />
                  <input
                    aria-label="Search graph"
                    placeholder={t("Find a source, investigator or file…")}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                  {query && (
                    <button
                      className="icon-button"
                      aria-label="Clear graph search"
                      onClick={() => setQuery("")}
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
                {query.trim() && (
                  <div
                    className="graph-search-results"
                    aria-label="Graph search results"
                  >
                    {matches.length ? (
                      matches.map((node) => (
                        <button
                          key={node.id}
                          type="button"
                          onClick={() => {
                            focusNode(node.id);
                            setQuery("");
                          }}
                        >
                          {node.source?.url ? (
                            <SiteIcon
                              url={node.source.url}
                              favicon={node.source.favicon}
                              size={14}
                            />
                          ) : (
                            <Search size={15} />
                          )}
                          <span>
                            {node.title}
                            <small>{node.source?.url || node.kind}</small>
                          </span>
                          <Focus size={14} />
                        </button>
                      ))
                    ) : (
                      <p>No matching graph items.</p>
                    )}
                  </div>
                )}
                <div className="graph-caption">
                  <strong>
                    {graph.sourceCount} source
                    {graph.sourceCount === 1 ? "" : "s"} · {graph.edges.length}{" "}
                    connections
                  </strong>
                  <span>
                    {graphMode === "overview"
                      ? "Sources and investigators · repeated checks grouped"
                      : "Every recorded source and check"}
                  </span>
                </div>
                <div
                  ref={setCanvas}
                  className="evidence-canvas"
                  aria-label="Evidence connections"
                  onKeyDown={(event) => {
                    if (["Enter", " "].includes(event.key)) {
                      const node = (event.target as HTMLElement).closest(
                        ".react-flow__node",
                      );
                      const id = node?.getAttribute("data-id");
                      if (id) {
                        event.preventDefault();
                        inspectSource(id);
                      } else {
                        const edgeId = (event.target as HTMLElement)
                          .closest(".react-flow__edge")
                          ?.getAttribute("data-id");
                        if (edgeId) {
                          event.preventDefault();
                          setSelectedEdge(edgeId);
                          setSelected("");
                        }
                      }
                    }
                  }}
                >
                  <ReactFlow
                    colorMode={resolvedTheme === "light" ? "light" : "dark"}
                    key={`${message.id}:${expanded}:${graphMode}`}
                    nodes={nodes}
                    edges={edges}
                    fitView
                    fitViewOptions={{
                      padding: 0.08,
                      minZoom: 0.65,
                      maxZoom: 0.9,
                    }}
                    onInit={(instance) => {
                      flow.current = instance;
                    }}
                    onMove={(_, viewport) =>
                      setZoom(Math.round(viewport.zoom * 100))
                    }
                    minZoom={0.08}
                    maxZoom={2}
                    nodesDraggable={false}
                    nodesConnectable={false}
                    edgesReconnectable={false}
                    deleteKeyCode={null}
                    onNodeClick={(_, node) => inspectSource(node.id)}
                    onEdgeClick={(_, edge) => {
                      setSelectedEdge(edge.id);
                      setSelected("");
                    }}
                    onPaneClick={() => {
                      setSelected("");
                      setSelectedEdge("");
                    }}
                  >
                    <Background gap={22} size={1} />
                    <GraphViewport
                      layoutKey={`${message.id}:${graphMode}:${columns}:${expanded}`}
                    />
                    <Controls showInteractive={false} />
                    <MiniMap
                      pannable
                      zoomable
                      nodeColor={(node) =>
                        node.className?.includes("needs-review")
                          ? "#b98040"
                          : node.className?.includes("source")
                            ? "#87a867"
                            : "#a7ada4"
                      }
                    />
                  </ReactFlow>
                </div>
                <div className="graph-navigation-hint">
                  <span>Drag to pan · Scroll to zoom</span>
                  <span aria-label="Graph zoom">{zoom}%</span>
                </div>
                <p className="graph-note">
                  Connections show recorded actions and citations. Listed or
                  referenced sources may still need checking; a connection alone
                  does not confirm a finding.
                </p>
                {connection && (
                  <article
                    className="source-inspector"
                    aria-label="Selected connection"
                  >
                    <strong>Recorded connection</strong>
                    <p>{connection.label}</p>
                    <div className="connection-links">
                      {[connection.source, connection.target].map((id) => (
                        <button
                          key={id}
                          type="button"
                          onClick={() => inspectSource(id)}
                        >
                          <GitBranch size={14} />
                          {graph.nodes.find((n) => n.id === id)?.title || id}
                        </button>
                      ))}
                    </div>
                  </article>
                )}
                {!connection && focused && (
                  <article
                    className="source-inspector"
                    aria-label="Selected graph item"
                  >
                    <div className="timeline-heading">
                      {focused.source?.url && (
                        <SiteIcon
                          url={focused.source.url}
                          favicon={focused.source.favicon}
                        />
                      )}
                      <strong>{focused.title}</strong>
                      <Status value={focused.status} />
                    </div>
                    {focused.source?.at && (
                      <time>
                        {new Date(focused.source.at).toLocaleString()}
                      </time>
                    )}
                    {focused.detail && (
                      <div className="inspector-detail">
                        <CaseMarkdown
                          chatId={chatId}
                          files={files}
                          sources={sources}
                        >
                          {focused.detail}
                        </CaseMarkdown>
                      </div>
                    )}
                    {focused.memberIds && (
                      <button
                        className="graph-review-checks"
                        onClick={() => {
                          setGraphMode("all");
                          setSelected(focused.memberIds![0]);
                        }}
                      >
                        View all {focused.memberIds.length} checks{" "}
                        <ExternalLink size={13} />
                      </button>
                    )}
                    {focused.source?.sha256 && (
                      <div className="source-hash">
                        <span>SHA-256</span>
                        <CopyControl
                          value={focused.source.sha256}
                          label="Copy file hash"
                        />
                        <code>{focused.source.sha256}</code>
                      </div>
                    )}
                    {focused.source?.url && (
                      <div className="source-inspector-actions">
                        <a
                          href={focused.source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <ExternalLink size={13} />
                          {focused.source.url}
                        </a>
                        <CopyControl value={focused.source.url} />
                      </div>
                    )}
                    {focused.source?.file &&
                      files.some((f) => f.name === focused.source?.file) &&
                      chatId && (
                        <a
                          href={`/api/chat/${chatId}/files?name=${encodeURIComponent(focused.source.file)}`}
                          download
                        >
                          Download attached file
                        </a>
                      )}
                  </article>
                )}
                {!!graph.sourceCount && (
                  <details className="source-directory">
                    <summary>Browse all {graph.sourceCount} sources</summary>
                    {graph.nodes
                      .filter((n) => n.kind === "source")
                      .map((node) => (
                        <SourceCard
                          key={node.id}
                          source={node.source!}
                          onInspect={inspectSource}
                          chatId={chatId}
                          files={files}
                        />
                      ))}
                  </details>
                )}
                {!!graph.edges.length && (
                  <details className="source-directory connection-directory">
                    <summary>
                      Browse all {graph.edges.length} connections
                    </summary>
                    <div className="connection-links">
                      {graph.edges.map((edge) => (
                        <button
                          key={edge.id}
                          type="button"
                          onClick={() => {
                            setSelectedEdge(edge.id);
                            setSelected("");
                          }}
                        >
                          <GitBranch size={14} />
                          <span>
                            {
                              graph.nodes.find((n) => n.id === edge.source)
                                ?.title
                            }
                            <small>
                              {edge.label} →{" "}
                              {
                                graph.nodes.find((n) => n.id === edge.target)
                                  ?.title
                              }
                            </small>
                          </span>
                        </button>
                      ))}
                    </div>
                  </details>
                )}
                {!graph.sourceCount && (
                  <p className="activity-empty">
                    No source records were saved for this reply. Earlier replies
                    may contain links without a recorded retrieval history.
                  </p>
                )}
              </>
            )}
            {tab === "output" && (
              <div className="run-output">
                <h3>{t("Investigator updates")}</h3>
                <ActivitySteps
                  steps={message.activity.filter((s) => s.kind === "update")}
                  {...sourceOptions}
                />
                <h3>
                  {message.status === "running"
                    ? t("Response so far")
                    : t("Investigation report")}
                </h3>
                <div className="output-report">
                  <CaseMarkdown chatId={chatId} files={files} sources={sources}>
                    {message.text ||
                      "The report will appear when the investigator responds."}
                  </CaseMarkdown>
                  {message.text && (
                    <CopyControl
                      value={message.text}
                      label={t("Copy investigation report")}
                    />
                  )}
                </div>
                <SpecialistAgents agents={message.agents} {...sourceOptions} />
                {message.error && (
                  <p className="error-banner">{message.error}</p>
                )}
              </div>
            )}
          </section>
          <footer className="run-footer">
            <Status value={message.status} />
            <span>
              {message.finishedAt
                ? `Ended ${new Date(message.finishedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                : `Started ${new Date(message.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
            </span>
          </footer>
        </>
      )}
    </aside>
  );
}
