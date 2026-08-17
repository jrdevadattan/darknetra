import type { ReactNode } from 'react';

import { InvestigatorShell } from '@/components/darknetra/investigator-shell';

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return <InvestigatorShell>{children}</InvestigatorShell>;
}
