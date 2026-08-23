import { CaseOverview } from '@/features/cases/case-overview';

export default async function CaseOverviewPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <CaseOverview caseId={caseId} />;
}
