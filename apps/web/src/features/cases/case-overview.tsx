"use client";

import { AsyncState } from "@/components/darknetra/async-state";
import { MetricLinkCard } from "@/components/darknetra/metric-link-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api/errors";

import { useCase } from "./queries";

export function CaseOverview({ caseId }: { caseId: string }) {
  const caseQuery = useCase(caseId);

  if (caseQuery.isPending) {
    return <AsyncState state="loading" />;
  }

  if (caseQuery.isError) {
    if (caseQuery.error instanceof ApiError && caseQuery.error.status === 0) {
      return (
        <AsyncState
          state="offline"
          title="Case service offline"
          description="The case overview cannot refresh because the API is unreachable."
        />
      );
    }

    return (
      <AsyncState
        state="error"
        title="Case overview unavailable"
        description="The case overview could not be loaded from the API."
      />
    );
  }

  const item = caseQuery.data;
  const processSteps = [
    {
      title: "Case intake",
      detail: "An authorized investigator creates the case, records scope, sensitivity, and source authority.",
    },
    {
      title: "Evidence collection",
      detail:
        "Evidence artifacts are collected through authenticated upload or approved source ingestion with custody and integrity metadata.",
    },
    {
      title: "Extraction and review",
      detail:
        "Entities, aliases, transactions, locations, and media observations are extracted, then queued for human review.",
    },
    {
      title: "Correlation and reporting",
      detail:
        "Accepted findings are linked into timelines, graph views, alerts, and export-ready investigation reports.",
    },
  ];
  const intelligenceStats = [
    { label: "Observations indexed", value: "34,982", detail: "34,982 observations indexed" },
    { label: "Linked entities", value: "12", detail: "12 linked entities" },
    { label: "Evidence artifacts", value: "9", detail: "9 evidence artifacts" },
    { label: "Review confidence", value: "91%", detail: "Cross-source signal agreement" },
  ];
  const evidenceLedger = [
    {
      id: "EV-1048",
      type: "Marketplace capture",
      custody: "Hash verified",
      signal: "Vendor handle, listing text, image fingerprint",
    },
    {
      id: "EV-1052",
      type: "Wallet observation",
      custody: "Chain reference linked",
      signal: "Payment address reuse and timing pattern",
    },
    {
      id: "EV-1061",
      type: "Message excerpt",
      custody: "Redaction ready",
      signal: "Contact alias, delivery region, product phrase",
    },
  ];
  const entitySignals = [
    { label: "Alias", value: "northlane_vendor", confidence: "96%" },
    { label: "Wallet", value: "bc1q9...7m2k", confidence: "89%" },
    { label: "Region", value: "Western corridor", confidence: "84%" },
    { label: "Substance term", value: "pressed tablets", confidence: "92%" },
  ];

  return (
    <div className="space-y-4">
      <AsyncState
        state="partial"
        title="Case intelligence package"
        description="The workspace ties case scope, custody metadata, evidence signals, entity extraction, graph correlation, alerts, and reporting into one auditable view."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {intelligenceStats.map((stat) => (
          <Card key={stat.label}>
            <CardHeader className="space-y-1">
              <CardDescription>{stat.label}</CardDescription>
              <CardTitle className="text-2xl">{stat.value}</CardTitle>
            </CardHeader>
            <CardContent className="text-muted-foreground text-xs">{stat.detail}</CardContent>
          </Card>
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricLinkCard
          label="Pending reviews"
          value={3}
          description={`${item.processStage} stage`}
          href={`/cases/${item.id}/links`}
        />
        <MetricLinkCard
          label="Open alerts"
          value={2}
          description="New correlation patterns awaiting disposition"
          href={`/cases/${item.id}/alerts`}
        />
        <MetricLinkCard
          label="Report package"
          value="Ready"
          description="Narrative, evidence index, timeline, and graph summary"
          href={`/cases/${item.id}/reports`}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle>Process flow</CardTitle>
            <CardDescription>How a case moves from intake to reportable findings.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {processSteps.map((step, index) => (
              <div key={step.title} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-[2.5rem_1fr]">
                <div className="flex size-8 items-center justify-center rounded-full bg-muted font-medium text-xs">
                  {index + 1}
                </div>
                <div>
                  <p className="font-medium">{step.title}</p>
                  <p className="mt-1 text-muted-foreground text-sm">{step.detail}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Case metadata</CardTitle>
            <CardDescription>Scope and custody context attached to this investigation.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">Case code</span>
              <span className="font-medium">{item.caseCode}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">Processing stage</span>
              <Badge variant="secondary">{item.processStage}</Badge>
            </div>
            <div>
              <p className="text-muted-foreground">Source authority</p>
              <p className="mt-1 rounded-lg border bg-muted/20 p-3">{item.sourceAuthority}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="text-muted-foreground">Created</p>
                <p className="font-medium">{new Date(item.createdAt).toLocaleString()}</p>
              </div>
              <div>
                <p className="text-muted-foreground">Updated</p>
                <p className="font-medium">{new Date(item.updatedAt).toLocaleString()}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Evidence ledger</CardTitle>
            <CardDescription>How collected artifacts stay traceable from intake to report.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {evidenceLedger.map((artifact) => (
              <div key={artifact.id} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">{artifact.id}</p>
                  <Badge variant="outline">{artifact.custody}</Badge>
                </div>
                <p className="mt-1 text-sm">{artifact.type}</p>
                <p className="mt-1 text-muted-foreground text-xs">{artifact.signal}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>Correlation graph</CardTitle>
            <CardDescription>
              Evidence, aliases, wallets, phrases, and alerts connected in one case-scoped graph.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="relative min-h-80 overflow-hidden rounded-xl border bg-muted/20 p-4">
              <svg viewBox="0 0 700 320" role="img" aria-label="Case correlation graph" className="h-full w-full">
                <line x1="350" y1="156" x2="130" y2="70" stroke="currentColor" strokeOpacity="0.25" />
                <line x1="350" y1="156" x2="585" y2="74" stroke="currentColor" strokeOpacity="0.25" />
                <line x1="350" y1="156" x2="150" y2="248" stroke="currentColor" strokeOpacity="0.25" />
                <line x1="350" y1="156" x2="560" y2="250" stroke="currentColor" strokeOpacity="0.25" />
                <line x1="130" y1="70" x2="150" y2="248" stroke="currentColor" strokeOpacity="0.15" />
                <line x1="585" y1="74" x2="560" y2="250" stroke="currentColor" strokeOpacity="0.15" />
                <GraphNode x={350} y={156} title="Case" detail={item.caseCode} emphasis />
                <GraphNode x={130} y={70} title="Alias" detail="northlane_vendor" />
                <GraphNode x={585} y={74} title="Wallet" detail="bc1q9...7m2k" />
                <GraphNode x={150} y={248} title="Evidence" detail="EV-1048 / EV-1061" />
                <GraphNode x={560} y={250} title="Alert" detail="Pattern spike" />
              </svg>
            </div>
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Entity extraction</CardTitle>
              <CardDescription>Readable findings with confidence, ready for analyst review.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {entitySignals.map((signal) => (
                <div key={signal.label} className="flex items-center justify-between gap-3 rounded-lg border p-3">
                  <div>
                    <p className="text-muted-foreground text-xs">{signal.label}</p>
                    <p className="font-medium">{signal.value}</p>
                  </div>
                  <Badge variant="secondary">{signal.confidence}</Badge>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Alert queue</CardTitle>
              <CardDescription>Prioritized signals for analyst review and escalation.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p className="rounded-lg border p-3">High: Wallet reuse overlaps with alias and product phrase.</p>
              <p className="rounded-lg border p-3">
                Medium: Image fingerprint appears across two marketplace captures.
              </p>
              <p className="rounded-lg border p-3">Review: Regional language pattern needs analyst confirmation.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
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
      <circle cx={x} cy={y} r={emphasis ? 50 : 42} className={emphasis ? "fill-primary" : "fill-background"} />
      <circle
        cx={x}
        cy={y}
        r={emphasis ? 50 : 42}
        className={emphasis ? "stroke-primary" : "stroke-border"}
        fill="none"
        strokeWidth="2"
      />
      <text
        x={x}
        y={y - 5}
        textAnchor="middle"
        className={emphasis ? "fill-primary-foreground font-medium text-xs" : "fill-foreground font-medium text-xs"}
      >
        {title}
      </text>
      <text
        x={x}
        y={y + 13}
        textAnchor="middle"
        className={emphasis ? "fill-primary-foreground text-[10px]" : "fill-muted-foreground text-[10px]"}
      >
        {detail}
      </text>
    </g>
  );
}
