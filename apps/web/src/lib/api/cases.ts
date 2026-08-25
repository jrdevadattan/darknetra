import { apiFetch } from "@/lib/api/client";
import type { GlobalRole } from "@/lib/api/auth";

export type CaseStatus = "OPEN" | "REVIEW" | "CLOSED";
export type CaseSensitivity = "STANDARD" | "RESTRICTED";

export interface ApiCase {
  id: string;
  case_code: string;
  title: string;
  status: CaseStatus;
  sensitivity: CaseSensitivity;
  owner_user_id: string;
  source_authority_summary: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface ApiCaseList {
  items: ApiCase[];
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface ApiCaseMember {
  user_id: string;
  username: string;
  display_name: string;
  roles: GlobalRole[];
  created_at: string;
}

export interface ApiCaseMemberList {
  items: ApiCaseMember[];
}

export interface CaseListParams {
  limit?: number;
  offset?: number;
}

export interface CaseCreatePayload {
  case_code: string;
  title: string;
  sensitivity: CaseSensitivity;
  source_authority_summary: string;
}

export function listCases(params: CaseListParams = {}): Promise<ApiCaseList> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const suffix = search.size ? `?${search.toString()}` : "";
  return apiFetch<ApiCaseList>(`/api/v1/cases${suffix}`);
}

export function getCase(caseId: string): Promise<ApiCase> {
  return apiFetch<ApiCase>(`/api/v1/cases/${encodeURIComponent(caseId)}`);
}

export function getCaseMembers(caseId: string): Promise<ApiCaseMemberList> {
  return apiFetch<ApiCaseMemberList>(`/api/v1/cases/${encodeURIComponent(caseId)}/members`);
}

export function createCase(payload: CaseCreatePayload): Promise<ApiCase> {
  return apiFetch<ApiCase>("/api/v1/cases", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
