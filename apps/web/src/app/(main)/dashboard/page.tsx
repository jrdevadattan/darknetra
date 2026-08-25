import { PageHeader } from "@/components/darknetra/page-header";
import { OverviewLiveView } from "@/features/overview/overview-live-view";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Authorized investigator workspace"
        title="Investigator overview"
        description="Live case inventory, work queues, evidence status, and processing signals for authenticated investigations."
      />
      <OverviewLiveView />
    </div>
  );
}
