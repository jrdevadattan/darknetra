import { PageHeader } from '@/components/darknetra/page-header';
import { CasesLiveView } from '@/features/cases/cases-live-view';

export default function CasesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Authorized case inventory"
        title="Cases"
        description="Search, filter, sort, and inspect cases visible to the authenticated investigator."
      />
      <CasesLiveView />
    </div>
  );
}
