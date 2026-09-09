import type {
  Activity,
  ChatAttachment,
  ChatMessage,
  RunSource,
} from "./chat-types";
import { sourceUrl } from "./run-activity";

export type EvidenceNode = {
  id: string;
  title: string;
  kind: "lead" | "agent" | "action" | "source" | "report" | "input";
  status: string;
  detail?: string;
  source?: RunSource;
  memberIds?: string[];
  x: number;
  y: number;
};
export type EvidenceEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
};

export function buildEvidenceGraph(
  message: ChatMessage,
  files: ChatAttachment[] = [],
) {
  const nodes: EvidenceNode[] = [];
  const edges: EvidenceEdge[] = [];
  const sources = new Map<string, RunSource>();
  const leadId = `lead:${message.id}`;
  const reportId = `report:${message.id}`;
  const addEdge = (source: string, target: string, label: string) => {
    const id = JSON.stringify([source, target, label]);
    if (source !== target && !edges.some((e) => e.id === id))
      edges.push({ id, source, target, label });
  };
  function addSource(source: RunSource) {
    const previous = sources.get(source.id);
    if (!previous || ["retrieved", "analysed"].includes(source.status))
      sources.set(source.id, { ...previous, ...source });
  }
  nodes.push({
    id: leadId,
    title: "Lead Investigator",
    kind: "lead",
    status: message.status,
    detail: "Coordinates the review and brings the recorded findings together.",
    x: 0,
    y: 0,
  });
  let row = 0;
  function actions(owner: string, steps: Activity[]) {
    for (const step of steps.filter(
      (s) =>
        s.kind !== "update" &&
        (s.sources?.length ||
          ["failed", "error", "unverified"].includes(s.status)),
    )) {
      const id = `action:${owner}:${step.id}`;
      nodes.push({
        id,
        title: step.label,
        kind: "action",
        status: step.status,
        detail: [step.detail, step.targetUrl, step.result, step.at]
          .filter(Boolean)
          .join("\n\n"),
        x: 640,
        y: row++ * 135,
      });
      addEdge(owner, id, "performed");
      for (const source of step.sources || []) {
        addSource(source);
        addEdge(
          id,
          source.id,
          source.status === "listed"
            ? "returned reference"
            : source.status === "analysed"
              ? "examined"
              : "retrieved",
        );
        if (source.parentId) addEdge(source.parentId, source.id, "lists");
      }
    }
  }
  actions(leadId, message.activity);
  for (const [index, agent] of (message.agents || []).entries()) {
    const id = `agent:${agent.id}`;
    nodes.push({
      id,
      title: agent.name,
      kind: "agent",
      status: agent.status,
      detail: [agent.task, agent.result].filter(Boolean).join("\n\n"),
      x: 320,
      y: index * 180,
    });
    addEdge(leadId, id, "assigned");
    actions(id, agent.activity || []);
    if (agent.result) addEdge(id, leadId, "reported back");
  }
  if (files.length) {
    const input = `input:${message.id}`;
    nodes.push({
      id: input,
      title: "Case attachments",
      kind: "input",
      status: "supplied",
      x: 320,
      y: ((message.agents?.length || 0) + 1) * 180,
    });
    addEdge(input, leadId, "provided for review");
    for (const file of files) {
      const id = `file:${file.name}`;
      addSource({
        id,
        title: file.label,
        file: file.name,
        kind: "file",
        status: "supplied",
        excerpt: `${file.size.toLocaleString()} bytes. Uploaded to this chat.`,
      });
      const source = sources.get(id)!;
      source.title = file.label;
      addEdge(input, id, "supplied");
    }
  }
  // A citation records what the report references; it does not prove its claim.
  const citations = new Set<string>();
  for (const match of message.text.matchAll(
    /\[[^\]]*\]\((https?:\/\/[^\s)]+)\)/g,
  )) {
    const url = sourceUrl(match[1]);
    if (url) {
      const id = `url:${url}`;
      citations.add(id);
      addSource({
        id,
        url,
        title: new URL(url).hostname,
        kind: "lead",
        status: "referenced",
        excerpt:
          "Referenced in the report. Retrieval details were not recorded for this URL.",
      });
    }
  }
  if (message.status !== "running" && message.text) {
    nodes.push({
      id: reportId,
      title:
        message.status === "done" ? "Investigation report" : "Partial report",
      kind: "report",
      status: message.status,
      detail: message.text,
      x: 1330,
      y: 0,
    });
    addEdge(leadId, reportId, "prepared");
    for (const source of sources.values()) {
      if (citations.has(source.id))
        addEdge(source.id, reportId, "cited in report");
    }
  }
  for (const [index, source] of [...sources.values()].entries()) {
    nodes.push({
      id: source.id,
      title: source.title,
      kind: "source",
      status: source.status,
      detail: source.excerpt,
      source,
      x: 980,
      y: index * 155,
    });
  }
  // Defensive validation keeps malformed imported history from creating ghost links.
  const ids = new Set(nodes.map((n) => n.id));
  return {
    nodes,
    edges: edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
    sourceCount: sources.size,
  };
}

export type EvidenceGraph = ReturnType<typeof buildEvidenceGraph>;

// Display projection only: the original action history and source statuses stay intact.
export function graphOverview(full: EvidenceGraph): EvidenceGraph {
  const nodes = full.nodes
    .filter((n) => n.kind !== "action")
    .map((n) => ({ ...n }));
  const actions = new Set(
    full.nodes.filter((n) => n.kind === "action").map((n) => n.id),
  );
  const edges = full.edges
    .filter((e) => !actions.has(e.source) && !actions.has(e.target))
    .map((e) => ({ ...e }));
  const groups = new Map<string, EvidenceNode[]>();
  for (const action of full.nodes.filter((n) => n.kind === "action")) {
    const owner = full.edges.find(
      (e) => e.target === action.id && e.label === "performed",
    )?.source;
    if (!owner) continue;
    const results = full.edges.filter((e) => e.source === action.id);
    for (const result of results) {
      const id = JSON.stringify([owner, result.target, result.label]);
      if (!edges.some((e) => e.id === id))
        edges.push({ ...result, id, source: owner });
    }
    if (["failed", "error", "unverified"].includes(action.status)) {
      const key = JSON.stringify([owner, action.status]);
      groups.set(key, [...(groups.get(key) || []), action]);
    }
  }
  for (const [key, members] of groups) {
    const [owner, status] = JSON.parse(key) as string[];
    const id = `checks:${key}`;
    nodes.push({
      id,
      kind: "action",
      title: `${members.length} ${status === "unverified" ? "unconfirmed" : "unsuccessful"} check${members.length === 1 ? "" : "s"}`,
      status,
      x: 0,
      y: 0,
      memberIds: members.map((n) => n.id),
      detail: members
        .map(
          (n) =>
            `**${n.title}**\n\n${n.detail || "No further details recorded."}`,
        )
        .join("\n\n---\n\n"),
    });
    edges.push({
      id: JSON.stringify([owner, id]),
      source: owner,
      target: id,
      label: "checks to review",
    });
  }
  return { nodes, edges, sourceCount: full.sourceCount };
}

export function layoutEvidenceGraph(
  graph: EvidenceGraph,
  columns = 2,
): EvidenceGraph {
  const nodes: EvidenceNode[] = [];
  let y = 0;
  // Short, centered rows replace the old single column of every tool action.
  const stages = [
    graph.nodes.filter((n) => n.kind === "lead"),
    graph.nodes.filter(
      (n) => ["agent", "input"].includes(n.kind) || n.memberIds,
    ),
    graph.nodes.filter((n) => n.kind === "action" && !n.memberIds),
    graph.nodes.filter((n) => n.kind === "source"),
    graph.nodes.filter((n) => n.kind === "report"),
  ];
  for (const stage of stages) {
    for (let i = 0; i < stage.length; i += columns) {
      const row = stage.slice(i, i + columns);
      row.forEach((node, column) =>
        nodes.push({ ...node, x: (column - (row.length - 1) / 2) * 270, y }),
      );
      y += 150;
    }
    if (stage.length) y += 24;
  }
  return { ...graph, nodes };
}
