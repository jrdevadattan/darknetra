import { describe, expect, it } from 'vitest';

import type { ApiCase } from '@/lib/api/cases';

import { CaseContractError, mapCaseSummary } from './queries';

const BASE_CASE: ApiCase = {
  id: '4d61f3aa-b46e-4ed2-b516-e91ec5930abc',
  case_code: 'CHD-2026-001',
  title: 'Synthetic narcotics case',
  status: 'OPEN',
  sensitivity: 'STANDARD',
  owner_user_id: '2b18f363-8fc0-44aa-8312-7f4792e663af',
  source_authority_summary: 'Authorized synthetic fixture for investigator training',
  created_at: '2026-08-17T09:30:00+05:30',
  updated_at: '2026-08-17T10:45:00+05:30',
  closed_at: null,
};

describe('mapCaseSummary', () => {
  it('maps the transport case into the retained UI shape and normalizes time', () => {
    expect(mapCaseSummary(BASE_CASE)).toEqual({
      id: BASE_CASE.id,
      title: BASE_CASE.title,
      status: 'OPEN',
      sensitivity: 'STANDARD',
      sourceClass: 'SYNTHETIC',
      owner: BASE_CASE.owner_user_id,
      evidenceCount: 0,
      pendingReviews: 0,
      openAlerts: 0,
      updatedAt: '2026-08-17T05:15:00.000Z',
    });
  });

  it('maps an explicit research-archive authority summary', () => {
    expect(
      mapCaseSummary({
        ...BASE_CASE,
        source_authority_summary: 'Research archive material authorized for controlled review',
      }).sourceClass,
    ).toBe('RESEARCH_ARCHIVE');
  });

  it.each([
    ['status', { status: 'PAUSED' }],
    ['sensitivity', { sensitivity: 'SECRET' }],
    ['source class', { source_authority_summary: 'Authorized case material' }],
    ['updated timestamp', { updated_at: 'not-a-date' }],
  ])('rejects an unsupported %s instead of silently coercing it', (_label, patch) => {
    expect(() => mapCaseSummary({ ...BASE_CASE, ...patch } as ApiCase)).toThrow(CaseContractError);
  });
});
