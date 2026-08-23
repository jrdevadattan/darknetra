import type { ReactNode } from 'react';

import { InvestigatorShell } from '@/components/darknetra/investigator-shell';
import { SessionGate } from '@/features/auth/session-gate';

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <SessionGate>
      <InvestigatorShell>{children}</InvestigatorShell>
    </SessionGate>
  );
}
