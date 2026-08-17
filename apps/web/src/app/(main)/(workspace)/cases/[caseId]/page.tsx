import { notFound } from 'next/navigation';

import { MetricLinkCard } from '@/components/darknetra/metric-link-card';
import { AsyncState } from '@/components/darknetra/async-state';
import { getFixtureCase } from '@/features/cases/fixtures';

export default async function CaseOverviewPage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  const item = getFixtureCase(caseId);
  if (!item) notFound();

  return (
    <div className="space-y-4">
      <AsyncState
        state="partial"
        title="Controlled case fixture"
        description="This case demonstrates navigation and review workflow only. Evidence integrity and analytic results are not simulated here."
      />
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricLinkCard label="Evidence artifacts" value={item.evidenceCount} description="Evidence Vault begins in Plan 03" href={`/cases/${item.id}/evidence`} />
        <MetricLinkCard label="Pending reviews" value={item.pendingReviews} description="Analyst decisions begin in the correlation plan" href={`/cases/${item.id}/links`} />
        <MetricLinkCard label="Open fixture alerts" value={item.openAlerts} description="Trend alerts begin in the graph/trends plan" href={`/cases/${item.id}/alerts`} />
      </div>
    </div>
  );
}
