'use client';

import { useQuery } from '@tanstack/react-query';

import {
  getCase,
  getCaseMembers,
  listCases,
  type ApiCase,
  type ApiCaseMemberList,
  type CaseListParams,
} from '@/lib/api/cases';
import { queryKeys } from '@/lib/query/keys';

import type { CaseSensitivity, CaseStatus, CaseSummary } from './types';

export class CaseContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CaseContractError';
  }
}

function caseStatus(value: unknown): CaseStatus {
  if (value === 'OPEN' || value === 'REVIEW' || value === 'CLOSED') return value;
  throw new CaseContractError(`Unsupported case status: ${String(value)}`);
}

function caseSensitivity(value: unknown): CaseSensitivity {
  if (value === 'STANDARD' || value === 'RESTRICTED') return value;
  throw new CaseContractError(`Unsupported case sensitivity: ${String(value)}`);
}

function sourceClass(summary: unknown): CaseSummary['sourceClass'] {
  if (typeof summary !== 'string') {
    throw new CaseContractError('Case source authority summary must be text.');
  }

  const normalized = summary.trim().toUpperCase().replace(/[\s-]+/g, '_');
  if (normalized.includes('RESEARCH_ARCHIVE')) return 'RESEARCH_ARCHIVE';
  if (normalized.includes('SYNTHETIC')) return 'SYNTHETIC';

  throw new CaseContractError(
    'Case source authority summary does not identify a supported source class.',
  );
}

function utcTimestamp(value: unknown): string {
  if (typeof value !== 'string') {
    throw new CaseContractError('Case updated timestamp must be text.');
  }
  const milliseconds = Date.parse(value);
  if (Number.isNaN(milliseconds)) {
    throw new CaseContractError(`Invalid case updated timestamp: ${value}`);
  }
  return new Date(milliseconds).toISOString();
}

export function mapCaseSummary(apiCase: ApiCase): CaseSummary {
  return {
    id: apiCase.id,
    title: apiCase.title,
    status: caseStatus(apiCase.status),
    sensitivity: caseSensitivity(apiCase.sensitivity),
    sourceClass: sourceClass(apiCase.source_authority_summary),
    owner: apiCase.owner_user_id,
    evidenceCount: 0,
    pendingReviews: 0,
    openAlerts: 0,
    updatedAt: utcTimestamp(apiCase.updated_at),
  };
}

export interface CaseSummaryList {
  items: CaseSummary[];
  limit: number;
  offset: number;
  hasMore: boolean;
}

export function useCases(params: CaseListParams = {}) {
  const normalizedParams: CaseListParams = {
    limit: params.limit ?? 25,
    offset: params.offset ?? 0,
  };

  return useQuery({
    queryKey: queryKeys.cases.list(normalizedParams),
    queryFn: () => listCases(normalizedParams),
    select: (response): CaseSummaryList => ({
      items: response.items.map(mapCaseSummary),
      limit: response.limit,
      offset: response.offset,
      hasMore: response.has_more,
    }),
  });
}

export function useCase(caseId: string) {
  return useQuery({
    queryKey: queryKeys.cases.detail(caseId),
    queryFn: () => getCase(caseId),
    select: mapCaseSummary,
    enabled: caseId.length > 0,
  });
}

export function useCaseMembers(caseId: string) {
  return useQuery<ApiCaseMemberList>({
    queryKey: queryKeys.cases.members(caseId),
    queryFn: () => getCaseMembers(caseId),
    enabled: caseId.length > 0,
  });
}
