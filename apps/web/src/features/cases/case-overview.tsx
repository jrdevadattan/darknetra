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

  return (
    <div className="space-y-4">
      <AsyncState
        state="partial"
        title="Case record is live"
        description="This view is backed by the case API. Evidence, review, and alert counters stay at zero until artifacts are attached to this case."
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricLinkCard
          label="Evidence artifacts"
          value={item.evidenceCount}
          description={item.collectionStatus}
          href={`/cases/${item.id}/evidence`}
        />
        <MetricLinkCard
          label="Pending reviews"
          value={item.pendingReviews}
          description={`${item.processStage} stage`}
          href={`/cases/${item.id}/links`}
        />
        <MetricLinkCard
          label="Open alerts"
          value={item.openAlerts}
          description="No unresolved alert dispositions"
          href={`/cases/${item.id}/alerts`}
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
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Video walkthrough script</CardTitle>
          <CardDescription>Short narration for explaining DARKNETRA case processing.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p>
            “DARKNETRA starts with an authorized case. The investigator records the case code, sensitivity, and source
            authority so every downstream action stays scoped to the approved investigation.”
          </p>
          <p>
            “Evidence is then collected through authenticated ingestion. Each artifact is tied to custody metadata,
            integrity checks, timestamps, and the user session that introduced it.”
          </p>
          <p>
            “The system extracts entities and activity signals, routes uncertain matches for analyst review, and keeps
            every accepted finding linked back to the evidence that supports it.”
          </p>
          <p>
            “At the end, analysts can move through the timeline, graph, alerts, and reports to produce a defensible
            investigation package without losing provenance.”
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
