import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { PageHeader } from "./page-header";

type GlobalSurface = "trends" | "sources" | "audit" | "settings" | "taxonomies";
type CaseSurface = "evidence" | "graph" | "alerts" | "entities" | "timeline" | "reports" | "links" | "activity";

const signalSeries = [
  { id: "window-1", value: 34 },
  { id: "window-2", value: 46 },
  { id: "window-3", value: 41 },
  { id: "window-4", value: 63 },
  { id: "window-5", value: 58 },
  { id: "window-6", value: 82 },
  { id: "window-7", value: 76 },
];
const termVelocity = [
  { label: "wallet reuse", value: 92 },
  { label: "image fingerprint", value: 78 },
  { label: "regional phrase", value: 64 },
  { label: "alias overlap", value: 88 },
];
const auditEvents = [
  ["09:12", "Session refreshed", "Token rotation completed with HttpOnly cookie boundary."],
  ["09:26", "Evidence attached", "EV-1048 registered with hash and custody metadata."],
  ["10:04", "Sensitive value revealed", "Wallet value reveal approved for case-owner review."],
  ["10:31", "Graph decision queued", "Alias-wallet relationship marked for analyst disposition."],
];
const sourceRows = [
  ["Marketplace capture", "Parser healthy", "92%", "Policy approved"],
  ["Wallet observation", "Chain reference linked", "89%", "Review ready"],
  ["Message excerpt", "Redaction ready", "84%", "Analyst scoped"],
];

const caseArtifacts = [
  ["EV-1048", "Marketplace capture", "Hash verified", "Alias, listing phrase, image fingerprint"],
  ["EV-1052", "Wallet observation", "Chain reference linked", "Payment address reuse and timing pattern"],
  ["EV-1061", "Message excerpt", "Redaction ready", "Contact alias, delivery region, product phrase"],
];
const entityRows = [
  ["Alias", "northlane_vendor", "96%"],
  ["Wallet", "bc1q9...7m2k", "89%"],
  ["Region", "Western corridor", "84%"],
  ["Term", "pressed tablets", "92%"],
];
const alertRows = [
  ["High", "Wallet reuse overlaps with alias and product phrase.", "Escalate"],
  ["Medium", "Image fingerprint appears across two marketplace captures.", "Review"],
  ["Review", "Regional language pattern needs analyst confirmation.", "Queue"],
];

export function GlobalOperationalSurface({ surface }: { surface: GlobalSurface }) {
  if (surface === "settings") {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Administration"
          title="System Settings"
          description="Security, retention, model, and deployment controls for the investigation workspace."
        />
        <MetricStrip
          metrics={[
            ["4", "policy groups", "security, retention, models, and deployment"],
            ["12", "controlled settings", "configuration values tracked by workspace scope"],
            ["100%", "access gated", "administrator-only configuration surface"],
          ]}
        />
        <DataPanel
          title="Configuration controls"
          description="Operational settings grouped by review area."
          headers={["Area", "Current control", "State"]}
          rows={[
            ["Security", "HttpOnly tokens, CSRF boundary, role checks", "Enforced"],
            ["Retention", "Case artifacts and audit history", "Active"],
            ["Models", "Extraction and scoring thresholds", "Review locked"],
            ["Deployment", "Production health and rollback checks", "Verified"],
          ]}
        />
        <FlowCard
          title="Configuration change flow"
          steps={["Admin request", "Policy check", "Change preview", "Audit record", "Apply control"]}
        />
      </div>
    );
  }

  if (surface === "taxonomies") {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Administration"
          title="Taxonomies"
          description="Normalized terms, source labels, regions, and entity classes used across extraction and graph review."
        />
        <MetricStrip
          metrics={[
            ["128", "normalized terms", "phrases grouped for extraction and trend review"],
            ["9", "entity classes", "alias, wallet, region, phrase, source, and artifact families"],
            ["6", "review queues", "taxonomy updates awaiting analyst confirmation"],
          ]}
        />
        <DataPanel
          title="Normalization matrix"
          description="How incoming language is converted into searchable case intelligence."
          headers={["Taxonomy", "Examples", "Use"]}
          rows={[
            ["Product terms", "pressed tablets, bulk listing, reship phrase", "Trend and alert matching"],
            ["Location terms", "corridor, region, route label", "Timeline and source grouping"],
            ["Identity terms", "alias, contact handle, wallet", "Graph relationship candidates"],
            ["Evidence terms", "capture, message, wallet observation", "Custody and report sections"],
          ]}
        />
        <FlowCard
          title="Taxonomy review flow"
          steps={["Term detected", "Normalize", "Map entity class", "Review conflict", "Publish version"]}
        />
      </div>
    );
  }

  if (surface === "audit") {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Governance"
          title="Audit"
          description="Traceable session, evidence, reveal, and analyst-review events for accountable investigations."
        />
        <MetricStrip
          metrics={[
            ["42", "audited actions", "session, case, evidence, and review events"],
            ["4", "protected reveals", "sensitive values accessed through approval paths"],
            ["100%", "custody coverage", "case actions tied to authenticated actors"],
          ]}
        />
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <TimelineCard title="Audit trail timeline" rows={auditEvents} />
          <CheckpointCard />
        </div>
      </div>
    );
  }

  if (surface === "sources") {
    return (
      <div className="space-y-6">
        <PageHeader
          eyebrow="Intelligence"
          title="Source Registry"
          description="Approved source classes, parser health, policy status, and confidence coverage."
        />
        <MetricStrip
          metrics={[
            ["3", "approved source classes", "capture, wallet, and message evidence streams"],
            ["91%", "coverage confidence", "weighted readiness across current source types"],
            ["0", "blocked collectors", "no source pipeline is marked unavailable"],
          ]}
        />
        <Card>
          <CardHeader>
            <CardTitle>Source readiness matrix</CardTitle>
            <CardDescription>Policy and parser status for evidence entering the workspace.</CardDescription>
          </CardHeader>
          <CardContent>
            <DataGrid headers={["Source class", "Pipeline state", "Confidence", "Control"]} rows={sourceRows} />
          </CardContent>
        </Card>
        <FlowCard
          title="Source-to-case flow"
          steps={["Approved source", "Capture envelope", "Integrity check", "Entity extraction", "Case graph"]}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Intelligence"
        title="Emerging Trends"
        description="Signal velocity, source diversity, and unresolved activity patterns across current investigations."
      />
      <MetricStrip
        metrics={[
          ["34,982", "observations indexed", "case-scoped records available for correlation"],
          ["18", "rising terms", "deduplicated signal clusters under review"],
          ["3", "open alerts", "activity patterns waiting for analyst disposition"],
        ]}
      />
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <TrendChartCard />
        <VelocityCard />
      </div>
      <FlowCard
        title="Investigation flow"
        steps={["Observation indexed", "Term normalized", "Entity extracted", "Pattern scored", "Alert reviewed"]}
      />
    </div>
  );
}

export function CaseOperationalSurface({ surface }: { surface: CaseSurface }) {
  const config = caseSurfaceConfig(surface);

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Case workspace" title={config.title} description={config.description} />
      <MetricStrip metrics={config.metrics} />
      {surface === "graph" ? <RelationshipGraphCard /> : null}
      {surface === "evidence" ? <EvidenceVaultCard /> : null}
      {surface === "alerts" ? <AlertQueueCard /> : null}
      {surface === "entities" ? <EntityExtractionCard /> : null}
      {surface === "reports" ? <ReportPackageCard /> : null}
      {surface === "timeline" ? <TimelineCard title="Case event timeline" rows={config.timelineRows} /> : null}
      {surface === "links" ? <LinkAnalysisCard /> : null}
      {surface === "activity" ? <ActivityCandidateCard /> : null}
      <FlowCard title={config.flowTitle} steps={config.flowSteps} />
    </div>
  );
}

function caseSurfaceConfig(surface: CaseSurface) {
  const baseMetrics: [string, string, string][] = [
    ["9", "evidence artifacts", "hash, custody, and source metadata attached"],
    ["12", "linked entities", "aliases, wallets, regions, terms, and artifacts"],
    ["91%", "signal agreement", "cross-source agreement after analyst review"],
  ];
  const timelineRows = [
    ["07:45", "Case opened", "Authority, sensitivity, and owner recorded."],
    ["08:12", "Evidence indexed", "Capture artifacts normalized into the evidence ledger."],
    ["09:18", "Graph projection", "Alias-wallet-evidence relationships generated for review."],
    ["10:40", "Report checkpoint", "Package readiness updated after alert disposition."],
  ];

  const configs = {
    evidence: {
      title: "Evidence vault",
      description: "Evidence inventory, integrity checks, custody movement, and extraction status in one case view.",
      metrics: baseMetrics,
      flowTitle: "Collection pipeline",
      flowSteps: ["Capture", "Hash verify", "Custody log", "Extract signals", "Attach to case"],
      timelineRows,
    },
    graph: {
      title: "Correlation graph",
      description: "Entity relationship map connecting case evidence, aliases, wallets, phrases, and alerts.",
      metrics: [
        ["12", "graph nodes", "case, alias, wallet, evidence, region, and alert nodes"],
        ["18", "candidate edges", "accepted and review-stage relationships"],
        ["7", "pending decisions", "analyst confirmation before final reporting"],
      ],
      flowTitle: "Graph decision flow",
      flowSteps: ["Entity detected", "Candidate link", "Confidence score", "Analyst review", "Accepted edge"],
      timelineRows,
    },
    alerts: {
      title: "Alerts",
      description: "Prioritized review queue for trend, entity, and activity signals that need analyst attention.",
      metrics: [
        ["3", "open alerts", "high, medium, and review-stage signals"],
        ["2", "resolved today", "alerts dispositioned into the case package"],
        ["0", "failed jobs", "processing queue is currently clear"],
      ],
      flowTitle: "Alert handling flow",
      flowSteps: ["Signal spike", "Deduplicate", "Severity score", "Analyst disposition", "Report note"],
      timelineRows,
    },
    entities: {
      title: "Entities",
      description:
        "Structured aliases, wallets, regions, product phrases, and confidence labels extracted from evidence.",
      metrics: baseMetrics,
      flowTitle: "Extraction flow",
      flowSteps: ["Raw evidence", "Normalize text", "Extract identifiers", "Score confidence", "Queue review"],
      timelineRows,
    },
    timeline: {
      title: "Timeline",
      description: "Case chronology joining capture time, observation time, analyst decisions, and report checkpoints.",
      metrics: [
        ["16", "timeline events", "capture, extraction, review, and report checkpoints"],
        ["4", "source windows", "observation ranges merged into UTC chronology"],
        ["1", "open review gap", "analyst confirmation still pending"],
      ],
      flowTitle: "Chronology flow",
      flowSteps: ["Capture time", "Observed time", "Ingested time", "Decision time", "Report time"],
      timelineRows,
    },
    reports: {
      title: "Report package",
      description: "Report-ready evidence index, graph summary, alert disposition, and analyst decision package.",
      metrics: [
        ["86%", "package readiness", "evidence, graph, alerts, and timeline assembled"],
        ["9", "indexed artifacts", "source-backed references included"],
        ["3", "review notes", "remaining analyst confirmations tracked"],
      ],
      flowTitle: "Reporting flow",
      flowSteps: ["Evidence index", "Graph summary", "Alert disposition", "Redaction review", "Export package"],
      timelineRows,
    },
    links: {
      title: "Link analysis",
      description: "Side-by-side relationship candidates with supporting and contradicting signals.",
      metrics: [
        ["18", "candidate links", "relationships scored from evidence overlap"],
        ["11", "supporting signals", "wallet, alias, phrase, and timing evidence"],
        ["4", "contradictions", "signals held for analyst review"],
      ],
      flowTitle: "Link review flow",
      flowSteps: ["Candidate pair", "Support signals", "Contradictions", "Decision", "Graph update"],
      timelineRows,
    },
    activity: {
      title: "Activity candidates",
      description: "Explainable activity candidates with signal decomposition and negative-context review.",
      metrics: [
        ["6", "activity candidates", "transactional and behavioral patterns under review"],
        ["4", "supporting clusters", "signals grouped by source and time"],
        ["2", "negative context flags", "contradictions preserved before escalation"],
      ],
      flowTitle: "Activity correlation flow",
      flowSteps: ["Observation", "Feature score", "Context check", "Candidate queue", "Analyst decision"],
      timelineRows,
    },
  } satisfies Record<
    CaseSurface,
    {
      title: string;
      description: string;
      metrics: [string, string, string][];
      flowTitle: string;
      flowSteps: string[];
      timelineRows: string[][];
    }
  >;

  return configs[surface];
}

function MetricStrip({ metrics }: { metrics: [string, string, string][] }) {
  return (
    <section className="grid gap-4 md:grid-cols-3" aria-label="Operational metrics">
      {metrics.map(([value, label, detail]) => (
        <Card key={label}>
          <CardHeader>
            <CardDescription>{label}</CardDescription>
            <CardTitle className="text-3xl">{value}</CardTitle>
          </CardHeader>
          <CardContent className="text-muted-foreground text-sm">{detail}</CardContent>
        </Card>
      ))}
    </section>
  );
}

function TrendChartCard() {
  const points = signalSeries.map((point, index) => `${40 + index * 78},${150 - point.value}`).join(" ");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity signal timeline</CardTitle>
        <CardDescription>Rising case-linked observations over the current review window.</CardDescription>
      </CardHeader>
      <CardContent>
        <svg viewBox="0 0 560 180" role="img" aria-label="Activity signal timeline chart" className="h-56 w-full">
          <path d="M30 150H540M30 40V150" fill="none" stroke="currentColor" strokeOpacity="0.18" />
          <polyline fill="none" points={points} stroke="currentColor" strokeWidth="4" />
          {signalSeries.map((point, index) => (
            <circle key={point.id} cx={40 + index * 78} cy={150 - point.value} r="5" fill="currentColor" />
          ))}
        </svg>
      </CardContent>
    </Card>
  );
}

function VelocityCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Term velocity</CardTitle>
        <CardDescription>Signal movement by normalized intelligence term.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {termVelocity.map((item) => (
          <div key={item.label} className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>{item.label}</span>
              <span className="font-medium">{item.value}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-foreground" style={{ width: `${item.value}%` }} />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function TimelineCard({ title, rows }: { title: string; rows: string[][] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>Ordered events with actor-visible operational context.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {rows.map(([time, event, detail]) => (
          <div key={`${time}-${event}`} className="grid gap-3 rounded-lg border p-3 sm:grid-cols-[72px_1fr]">
            <Badge variant="outline">{time}</Badge>
            <div>
              <p className="font-medium">{event}</p>
              <p className="text-muted-foreground text-sm">{detail}</p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function CheckpointCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Integrity checkpoints</CardTitle>
        <CardDescription>Controls that keep case actions accountable.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {["Session controls", "Case-scoped authorization", "Custody hash verification", "Sensitive reveal logging"].map(
          (item) => (
            <div key={item} className="flex items-center justify-between rounded-lg border p-3">
              <span>{item}</span>
              <Badge variant="secondary">Verified</Badge>
            </div>
          ),
        )}
      </CardContent>
    </Card>
  );
}

function EvidenceVaultCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Custody chain</CardTitle>
        <CardDescription>Evidence artifacts with integrity status and extracted signals.</CardDescription>
      </CardHeader>
      <CardContent>
        <DataGrid headers={["ID", "Artifact", "Integrity", "Signals"]} rows={caseArtifacts} />
      </CardContent>
    </Card>
  );
}

function DataPanel({
  title,
  description,
  headers,
  rows,
}: {
  title: string;
  description: string;
  headers: string[];
  rows: string[][];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <DataGrid headers={headers} rows={rows} />
      </CardContent>
    </Card>
  );
}

function RelationshipGraphCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Entity relationship map</CardTitle>
        <CardDescription>Case-scoped graph showing the main evidence relationships.</CardDescription>
      </CardHeader>
      <CardContent>
        <svg viewBox="0 0 760 320" role="img" aria-label="Entity relationship map" className="h-80 w-full">
          <line x1="380" y1="150" x2="150" y2="70" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
          <line x1="380" y1="150" x2="610" y2="72" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
          <line x1="380" y1="150" x2="160" y2="255" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
          <line x1="380" y1="150" x2="600" y2="255" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
          <GraphNode x={380} y={150} title="Case" detail="DN-INT-7842" emphasis />
          <GraphNode x={150} y={70} title="Alias" detail="northlane_vendor" />
          <GraphNode x={610} y={72} title="Wallet" detail="bc1q9...7m2k" />
          <GraphNode x={160} y={255} title="Evidence" detail="EV-1048 / EV-1061" />
          <GraphNode x={600} y={255} title="Alert" detail="Pattern spike" />
        </svg>
      </CardContent>
    </Card>
  );
}

function GraphNode({
  x,
  y,
  title,
  detail,
  emphasis = false,
}: {
  x: number;
  y: number;
  title: string;
  detail: string;
  emphasis?: boolean;
}) {
  return (
    <g>
      <circle cx={x} cy={y} r={emphasis ? 58 : 50} fill={emphasis ? "currentColor" : "transparent"} opacity="0.1" />
      <circle cx={x} cy={y} r={emphasis ? 50 : 42} fill="white" stroke="currentColor" strokeWidth="2" />
      <text x={x} y={y - 4} textAnchor="middle" className="fill-current font-semibold text-sm">
        {title}
      </text>
      <text x={x} y={y + 16} textAnchor="middle" className="fill-current text-xs">
        {detail}
      </text>
    </g>
  );
}

function AlertQueueCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Priority queue</CardTitle>
        <CardDescription>Signals ranked for review and escalation.</CardDescription>
      </CardHeader>
      <CardContent>
        <DataGrid headers={["Severity", "Signal", "Action"]} rows={alertRows} />
      </CardContent>
    </Card>
  );
}

function EntityExtractionCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Structured findings</CardTitle>
        <CardDescription>Entities extracted from evidence and prepared for analyst review.</CardDescription>
      </CardHeader>
      <CardContent>
        <DataGrid headers={["Type", "Value", "Confidence"]} rows={entityRows} />
      </CardContent>
    </Card>
  );
}

function ReportPackageCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Package readiness</CardTitle>
        <CardDescription>Report sections assembled from evidence-backed case work.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {[
          ["Evidence index", "Complete"],
          ["Graph summary", "Ready"],
          ["Alert disposition", "In review"],
          ["Redaction pass", "Queued"],
        ].map(([section, state]) => (
          <div key={section} className="rounded-lg border p-3">
            <p className="font-medium">{section}</p>
            <p className="text-muted-foreground text-sm">{state}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function LinkAnalysisCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Candidate comparison</CardTitle>
        <CardDescription>Relationship candidates preserve supporting and contradicting context.</CardDescription>
      </CardHeader>
      <CardContent>
        <DataGrid
          headers={["Candidate", "Supporting signals", "Contradictions", "Decision"]}
          rows={[
            ["Alias -> wallet", "5", "1", "Review"],
            ["Phrase -> listing", "4", "0", "Accept"],
            ["Region -> alias", "2", "2", "Hold"],
          ]}
        />
      </CardContent>
    </Card>
  );
}

function ActivityCandidateCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Feature decomposition</CardTitle>
        <CardDescription>Activity candidates are explained before escalation.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-3">
        {["Timing overlap", "Wallet reuse", "Phrase recurrence"].map((item, index) => (
          <div key={item} className="rounded-lg border p-3">
            <p className="font-medium">{item}</p>
            <p className="text-muted-foreground text-sm">{[82, 89, 76][index]}% contribution</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function FlowCard({ title, steps }: { title: string; steps: string[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>How records move from collection to decision.</CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="grid gap-3 md:grid-cols-5">
          {steps.map((step, index) => (
            <li key={step} className="rounded-lg border p-3">
              <Badge variant="outline">Step {index + 1}</Badge>
              <p className="mt-3 font-medium">{step}</p>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function DataGrid({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-hidden rounded-lg border">
      <div
        className="grid bg-muted/60 font-medium text-sm"
        style={{ gridTemplateColumns: `repeat(${headers.length}, minmax(0, 1fr))` }}
      >
        {headers.map((header) => (
          <div key={header} className="border-r p-3 last:border-r-0">
            {header}
          </div>
        ))}
      </div>
      {rows.map((row) => (
        <div
          key={row.join("-")}
          className="grid border-t text-sm"
          style={{ gridTemplateColumns: `repeat(${headers.length}, minmax(0, 1fr))` }}
        >
          {row.map((cell) => (
            <div key={cell} className="border-r p-3 last:border-r-0">
              {cell}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
