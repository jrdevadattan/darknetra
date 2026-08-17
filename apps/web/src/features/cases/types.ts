import type { SourceClass } from '@/components/darknetra/source-class-badge';

export type CaseStatus = 'OPEN' | 'REVIEW' | 'CLOSED';
export type CaseSensitivity = 'STANDARD' | 'RESTRICTED';

export interface CaseSummary {
  id: string;
  title: string;
  status: CaseStatus;
  sensitivity: CaseSensitivity;
  sourceClass: SourceClass;
  owner: string;
  evidenceCount: number;
  pendingReviews: number;
  openAlerts: number;
  updatedAt: string;
}
