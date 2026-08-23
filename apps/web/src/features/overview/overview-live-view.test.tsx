import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OverviewLiveView } from './overview-live-view';

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function renderWithQuery(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('OverviewLiveView', () => {
  it('derives active and recent cases from the live case API without fixture fallback', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        items: [
          {
            id: '4d61f3aa-b46e-4ed2-b516-e91ec5930abc',
            case_code: 'CHD-2026-001',
            title: 'Live synthetic case',
            status: 'OPEN',
            sensitivity: 'STANDARD',
            owner_user_id: '2b18f363-8fc0-44aa-8312-7f4792e663af',
            source_authority_summary: 'Authorized synthetic training source',
            created_at: '2026-08-17T09:30:00Z',
            updated_at: '2026-08-17T10:45:00Z',
            closed_at: null,
          },
          {
            id: '541418a0-f030-448e-81c9-cdd9ad397580',
            case_code: 'CHD-2026-002',
            title: 'Closed research case',
            status: 'CLOSED',
            sensitivity: 'RESTRICTED',
            owner_user_id: 'feac7955-9caa-4834-a30c-b4636fccb364',
            source_authority_summary: 'Research archive authorized for review',
            created_at: '2026-08-16T09:30:00Z',
            updated_at: '2026-08-16T10:45:00Z',
            closed_at: '2026-08-16T11:00:00Z',
          },
        ],
        limit: 100,
        offset: 0,
        has_more: false,
      }),
    );

    renderWithQuery(<OverviewLiveView />);

    expect(await screen.findByRole('link', { name: /Active cases: 1\./i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Live synthetic case' })).toHaveAttribute(
      'href',
      '/cases/4d61f3aa-b46e-4ed2-b516-e91ec5930abc',
    );
    expect(screen.queryByText('Alias correlation training case')).not.toBeInTheDocument();
  });

  it('renders an explicit offline state instead of fixture metrics', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('network unavailable'));

    renderWithQuery(<OverviewLiveView />);

    expect(await screen.findByText('Overview service offline')).toBeInTheDocument();
  });
});
