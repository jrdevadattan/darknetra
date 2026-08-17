'use client';

import { AsyncState } from '@/components/darknetra/async-state';
import { MetricLinkCard } from '@/components/darknetra/metric-link-card';
import { ApiError } from '@/lib/api/errors';

import { useCase } from './queries';

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

  return (
    <div className="space-y-4">
      <AsyncState
        state="partial"
        title="Case analytics not yet available"
        description="Plan 02 now uses the live case record. Evidence, review, and alert counts remain zero until their owning plans add those APIs."
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricLinkCard
          label="Evidence artifacts"
          value={item.evidenceCount}
          description="Evidence Vault begins in Plan 03"
          href={`/cases/${item.id}/evidence`}
        />
        <MetricLinkCard
          label="Pending reviews"
          value={item.pendingReviews}
          description="Analyst decisions begin in the correlation plan"
          href={`/cases/${item.id}/links`}
        />
        <MetricLinkCard
          label="Open alerts"
          value={item.openAlerts}
          description="Trend alerts begin in the graph/trends plan"
          href={`/cases/${item.id}/alerts`}
        />
      </div>
    </div>
  );
}
