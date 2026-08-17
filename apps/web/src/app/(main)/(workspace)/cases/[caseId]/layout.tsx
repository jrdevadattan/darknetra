import type { ReactNode } from 'react';
import { notFound } from 'next/navigation';

import { CaseTabs } from '@/components/darknetra/case-tabs';
import { PageHeader } from '@/components/darknetra/page-header';
import { SourceClassBadge } from '@/components/darknetra/source-class-badge';
import { Badge } from '@/components/ui/badge';
import { getFixtureCase } from '@/features/cases/fixtures';

export default async function CaseLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  const currentCase = getFixtureCase(caseId);
  if (!currentCase) notFound();

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={currentCase.id}
        title={currentCase.title}
        description={`Fixture owner: ${currentCase.owner} · Sensitivity: ${currentCase.sensitivity}`}
        actions={
          <>
            <Badge variant="secondary">{currentCase.status}</Badge>
            <SourceClassBadge sourceClass={currentCase.sourceClass} />
          </>
        }
      />
      <CaseTabs caseId={currentCase.id} />
      {children}
    </div>
  );
}
