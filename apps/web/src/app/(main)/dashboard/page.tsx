import Link from 'next/link';

import { AsyncState } from '@/components/darknetra/async-state';
import { MetricLinkCard } from '@/components/darknetra/metric-link-card';
import { PageHeader } from '@/components/darknetra/page-header';
import { SourceClassBadge } from '@/components/darknetra/source-class-badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getFixtureOverviewSnapshot } from '@/features/overview/fixture-overview';

export default function DashboardPage() {
  const snapshot = getFixtureOverviewSnapshot();
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Controlled demonstration environment"
        title="Investigator overview"
        description="Action-oriented fixture queues for validating DARKNETRA workflows before the evidence and analytics APIs are connected."
        actions={<SourceClassBadge sourceClass="SYNTHETIC" />}
      />
      <AsyncState
        state="partial"
        title="Fixture-backed interface"
        description="Counts on this screen are controlled demonstration data. Live case, evidence, alert, and worker state begins in later implementation plans."
      />
      <section aria-label="Investigator work queues" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {snapshot.metrics.map((metric) => <MetricLinkCard key={metric.id} {...metric} />)}
      </section>
      <Card>
        <CardHeader>
          <CardTitle>Recent controlled cases</CardTitle>
          <CardDescription>Only synthetic or research-archive fixtures are shown in Plan 01.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {snapshot.recentCases.map((item) => (
            <div key={item.id} className="flex flex-col justify-between gap-3 rounded-lg border p-3 sm:flex-row sm:items-center">
              <div className="min-w-0">
                <Link href={`/cases/${item.id}`} className="font-medium hover:underline">{item.title}</Link>
                <p className="mt-1 text-muted-foreground text-xs">{item.id} · {item.owner}</p>
              </div>
              <div className="flex items-center gap-2"><SourceClassBadge sourceClass={item.sourceClass} /></div>
            </div>
          ))}
          <Button asChild variant="outline"><Link href="/cases">Open case inventory</Link></Button>
        </CardContent>
      </Card>
    </div>
  );
}
