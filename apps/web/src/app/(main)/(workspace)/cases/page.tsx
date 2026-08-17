import { PageHeader } from '@/components/darknetra/page-header';
import { CasesTable } from '@/features/cases/cases-table';
import { FIXTURE_CASES } from '@/features/cases/fixtures';

export default function CasesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Fixture inventory"
        title="Cases"
        description="Search, filter, sort, and inspect controlled cases. Persistent case APIs and membership enforcement begin in Plan 02."
      />
      <CasesTable cases={FIXTURE_CASES} />
    </div>
  );
}
