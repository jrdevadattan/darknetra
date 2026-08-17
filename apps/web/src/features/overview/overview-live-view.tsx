'use client';

import Link from 'next/link';

import { AsyncState } from '@/components/darknetra/async-state';
import { MetricLinkCard } from '@/components/darknetra/metric-link-card';
import { SourceClassBadge } from '@/components/darknetra/source-class-badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useCases } from '@/features/cases/queries';
import { ApiError } from '@/lib/api/errors';

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
          description="The case API could not be reached. No fixture metrics are substituted."
        />
      );
    }

    if (
      casesQuery.error instanceof ApiError &&
      (casesQuery.error.status === 401 || casesQuery.error.status === 403)
    ) {
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

  const cases = casesQuery.data.items;
  const activeCases = cases.filter((item) => item.status !== 'CLOSED').length;
  const recentCases = [...cases]
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt))
    .slice(0, 4);

  const metrics = [
    {
      id: 'active-cases',
      label: 'Active cases',
      value: activeCases,
      description: 'Open or review-stage cases visible to this investigator',
      href: '/cases',
    },
    {
      id: 'integrity-warnings',
      label: 'Integrity warnings',
      value: 0,
      description: 'Evidence integrity metrics arrive with the Evidence Vault in Plan 03',
      href: '/cases',
    },
    {
      id: 'pending-reviews',
      label: 'Pending link reviews',
      value: 0,
      description: 'Link-review metrics arrive with the correlation workflow',
      href: '/cases',
    },
    {
      id: 'open-alerts',
      label: 'Open alerts',
      value: 0,
      description: 'Trend alert metrics arrive with the graph and trends plan',
      href: '/intelligence/trends',
    },
    {
      id: 'failed-jobs',
      label: 'Failed jobs',
      value: 0,
      description: 'Durable processing-job metrics arrive with evidence ingestion',
      href: '/system/health',
    },
  ];

  return (
    <div className="space-y-6">
      <AsyncState
        state="partial"
        title="Live cases, later-plan analytics"
        description="Case inventory is live. Evidence, correlation, alert, and worker metrics remain zero until their owning plans add those APIs."
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
                    {item.id} · {item.owner}
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
