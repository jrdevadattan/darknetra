import type { SourceClass } from "@/components/darknetra/source-class-badge";

export type CaseStatus = "OPEN" | "REVIEW" | "CLOSED";
export type CaseSensitivity = "STANDARD" | "RESTRICTED";

export interface CaseSummary {
  caseCode: string;
  collectionStatus: string;
  createdAt: string;
  id: string;
  title: string;
  status: CaseStatus;
  sensitivity: CaseSensitivity;
  sourceClass: SourceClass;
  sourceAuthority: string;
  owner: string;
  evidenceCount: number;
  pendingReviews: number;
  openAlerts: number;
  processStage: string;
  updatedAt: string;
}
