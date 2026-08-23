import { PageHeader } from '@/components/darknetra/page-header';
import { OverviewLiveView } from '@/features/overview/overview-live-view';

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Authorized investigator workspace"
        title="Investigator overview"
        description="Live case inventory with explicit placeholders for evidence, correlation, alert, and worker metrics owned by later plans."
      />
      <OverviewLiveView />
    </div>
  );
}
