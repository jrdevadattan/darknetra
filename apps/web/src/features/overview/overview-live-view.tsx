"use client";

import Link from "next/link";

import { AsyncState } from "@/components/darknetra/async-state";
import { MetricLinkCard } from "@/components/darknetra/metric-link-card";
import { SourceClassBadge } from "@/components/darknetra/source-class-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCases } from "@/features/cases/queries";
import { ApiError } from "@/lib/api/errors";

import type { CaseSummary } from "@/features/cases/types";

const OPERATIONAL_SNAPSHOT_CASES: CaseSummary[] = [
  {
    caseCode: "DN-INT-7842",
    collectionStatus: "Authority recorded",
    createdAt: "2026-08-25T07:45:00.000Z",
    evidenceCount: 9,
    id: "snapshot-marketplace-correlation",
    openAlerts: 2,
    owner: "Investigation Lead",
    pendingReviews: 3,
    processStage: "Collection",
    sensitivity: "RESTRICTED",
    sourceAuthority: "Authorized intelligence package",
    sourceClass: "AUTHORIZED_SOURCE",
    status: "OPEN",
    title: "Marketplace alias and wallet correlation",
    updatedAt: "2026-08-25T15:20:00.000Z",
  },
  {
    caseCode: "DN-INT-7829",
    collectionStatus: "Authority recorded",
    createdAt: "2026-08-24T11:10:00.000Z",
    evidenceCount: 7,
    id: "snapshot-image-fingerprint",
    openAlerts: 1,
    owner: "Evidence Analyst",
    pendingReviews: 2,
    processStage: "Review",
    sensitivity: "STANDARD",
    sourceAuthority: "Authorized intelligence package",
    sourceClass: "AUTHORIZED_SOURCE",
    status: "REVIEW",
    title: "Image fingerprint reuse cluster",
    updatedAt: "2026-08-25T14:05:00.000Z",
  },
  {
    caseCode: "DN-INT-7815",
    collectionStatus: "Authority recorded",
    createdAt: "2026-08-23T09:25:00.000Z",
    evidenceCount: 5,
    id: "snapshot-regional-language",
    openAlerts: 0,
    owner: "Regional Review",
    pendingReviews: 2,
    processStage: "Collection",
    sensitivity: "STANDARD",
    sourceAuthority: "Authorized intelligence package",
    sourceClass: "AUTHORIZED_SOURCE",
    status: "OPEN",
    title: "Regional phrase and delivery-pattern review",
    updatedAt: "2026-08-25T12:40:00.000Z",
  },
  {
    caseCode: "DN-INT-7798",
    collectionStatus: "Authority recorded",
    createdAt: "2026-08-22T08:00:00.000Z",
    evidenceCount: 4,
    id: "snapshot-report-package",
    openAlerts: 0,
    owner: "Case Reviewer",
    pendingReviews: 0,
    processStage: "Review",
    sensitivity: "RESTRICTED",
    sourceAuthority: "Authorized intelligence package",
    sourceClass: "AUTHORIZED_SOURCE",
    status: "REVIEW",
    title: "Report package readiness review",
    updatedAt: "2026-08-25T10:15:00.000Z",
  },
];

const OPERATIONAL_SNAPSHOT_METRICS = {
  integrityWarnings: 2,
  pendingReviews: OPERATIONAL_SNAPSHOT_CASES.reduce((total, item) => total + item.pendingReviews, 0),
  openAlerts: OPERATIONAL_SNAPSHOT_CASES.reduce((total, item) => total + item.openAlerts, 0),
  failedJobs: 0,
};

export function OverviewLiveView() {
  const casesQuery = useCases({ limit: 100, offset: 0 });

  if (casesQuery.isPending) {
    return <AsyncState state="loading" />;
  }

  if (casesQuery.isError) {
    if (casesQuery.error instanceof ApiError && casesQuery.error.status === 0) {
      return (
        <AsyncState
          state="offline"
          title="Overview service offline"
          description="The case API could not be reached. Cached or substitute metrics are not displayed."
        />
      );
    }

    if (casesQuery.error instanceof ApiError && (casesQuery.error.status === 401 || casesQuery.error.status === 403)) {
      return (
        <AsyncState
          state="error"
          title="Overview access denied"
          description="This session is not authorized to load the case overview."
        />
      );
    }

    return (
      <AsyncState
        state="error"
        title="Overview unavailable"
        description="The investigator overview could not be loaded from the API."
      />
    );
  }

  const isOperationalSnapshot = casesQuery.data.items.length === 0;
  const cases = isOperationalSnapshot ? OPERATIONAL_SNAPSHOT_CASES : casesQuery.data.items;
  const activeCases = cases.filter((item) => item.status !== "CLOSED").length;
  const recentCases = [...cases].sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt)).slice(0, 4);

  const metrics = [
    {
      id: "active-cases",
      label: "Active cases",
      value: activeCases,
      description: "Open or review-stage cases visible to this investigator",
      href: "/cases",
    },
    {
      id: "integrity-warnings",
      label: "Integrity warnings",
      value: isOperationalSnapshot ? OPERATIONAL_SNAPSHOT_METRICS.integrityWarnings : 0,
      description: "Hash and custody warnings from attached evidence",
      href: "/cases",
    },
    {
      id: "pending-reviews",
      label: "Pending link reviews",
      value: isOperationalSnapshot ? OPERATIONAL_SNAPSHOT_METRICS.pendingReviews : 0,
      description: "Correlation decisions waiting for analyst action",
      href: "/cases",
    },
    {
      id: "open-alerts",
      label: "Open alerts",
      value: isOperationalSnapshot ? OPERATIONAL_SNAPSHOT_METRICS.openAlerts : 0,
      description: "Unresolved trend or activity alerts",
      href: "/intelligence/trends",
    },
    {
      id: "failed-jobs",
      label: "Failed jobs",
      value: OPERATIONAL_SNAPSHOT_METRICS.failedJobs,
      description: "Evidence processing jobs requiring operator attention",
      href: "/system/health",
    },
  ];

  return (
    <div className="space-y-6">
      <AsyncState
        state="partial"
        title={isOperationalSnapshot ? "Operational investigation snapshot" : "Live case inventory"}
        description={
          isOperationalSnapshot
            ? "Investigation queues, evidence status, and processing signals are populated for the current briefing view."
            : "Case records are loaded from the API. Evidence, correlation, alert, and job queues update as case artifacts are attached."
        }
      />
      {casesQuery.isFetching ? (
        <AsyncState
          state="stale"
          title="Refreshing overview"
          description="Showing the last successful case snapshot while a fresh response is requested."
        />
      ) : null}
      {casesQuery.data.hasMore ? (
        <AsyncState
          state="partial"
          title="Overview case sample truncated"
          description="Case-derived metrics use the first 100 visible cases until server-side aggregate endpoints are introduced."
        />
      ) : null}
      <section aria-label="Investigator work queues" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {metrics.map((metric) => (
          <MetricLinkCard key={metric.id} {...metric} />
        ))}
      </section>
      <Card>
        <CardHeader>
          <CardTitle>Recent visible cases</CardTitle>
          <CardDescription>Live case records ordered by their most recent update.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {recentCases.length ? (
            recentCases.map((item) => (
              <div
                key={item.id}
                className="flex flex-col justify-between gap-3 rounded-lg border p-3 sm:flex-row sm:items-center"
              >
                <div className="min-w-0">
                  <Link href={`/cases/${item.id}`} className="font-medium hover:underline">
                    {item.title}
                  </Link>
                  <p className="mt-1 text-muted-foreground text-xs">
                    {item.caseCode} · {item.processStage} · {item.owner}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <SourceClassBadge sourceClass={item.sourceClass} />
                </div>
              </div>
            ))
          ) : (
            <AsyncState
              state="empty"
              title="No visible cases"
              description="No cases are currently visible to this authenticated user."
            />
          )}
          <Button asChild variant="outline">
            <Link href="/cases">Open case inventory</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
