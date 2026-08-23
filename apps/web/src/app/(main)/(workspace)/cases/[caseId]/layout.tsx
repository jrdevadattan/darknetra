import type { ReactNode } from 'react';

import { CaseShell } from '@/features/cases/case-shell';

export default async function CaseLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <CaseShell caseId={caseId}>{children}</CaseShell>;
}
