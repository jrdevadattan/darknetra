import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CaseShell } from './case-shell';
import { CasesLiveView } from './cases-live-view';

vi.mock('next/navigation', () => ({
  usePathname: () => '/cases/4d61f3aa-b46e-4ed2-b516-e91ec5930abc',
}));

const fetchMock = vi.fn();

const API_CASE = {
  id: '4d61f3aa-b46e-4ed2-b516-e91ec5930abc',
  case_code: 'CHD-2026-001',
  title: 'Synthetic narcotics case',
  status: 'OPEN',
  sensitivity: 'STANDARD',
  owner_user_id: '2b18f363-8fc0-44aa-8312-7f4792e663af',
  source_authority_summary: 'Authorized synthetic fixture for investigator training',
  created_at: '2026-08-17T09:30:00Z',
  updated_at: '2026-08-17T10:45:00Z',
  closed_at: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function renderWithQuery(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
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

describe('CasesLiveView', () => {
  it('renders live API cases through the retained table interface', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ items: [API_CASE], limit: 25, offset: 0, has_more: false }),
    );

    renderWithQuery(<CasesLiveView />);

    expect(screen.getByTestId('async-state-loading')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: API_CASE.title })).toHaveAttribute(
      'href',
      `/cases/${API_CASE.id}`,
    );
    expect(screen.queryByText(/fixture inventory/i)).not.toBeInTheDocument();
  });

  it('shows an explicit empty state when the visible case list is empty', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ items: [], limit: 25, offset: 0, has_more: false }),
    );

    renderWithQuery(<CasesLiveView />);

    expect(await screen.findByText('No visible cases')).toBeInTheDocument();
  });

  it('shows access denied instead of fixture fallback on authorization failure', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'permission denied' }, 403));

    renderWithQuery(<CasesLiveView />);

    expect(await screen.findByText('Case access denied')).toBeInTheDocument();
    expect(screen.queryByText('Alias correlation training case')).not.toBeInTheDocument();
  });

  it('shows an offline state when the API cannot be reached', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('network unavailable'));

    renderWithQuery(<CasesLiveView />);

    expect(await screen.findByText('Case service offline')).toBeInTheDocument();
  });
});

describe('CaseShell', () => {
  it('renders a live case header and its child route when the case is visible', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(API_CASE));

    renderWithQuery(
      <CaseShell caseId={API_CASE.id}>
        <p>Child route content</p>
      </CaseShell>,
    );

    expect(await screen.findByRole('heading', { name: API_CASE.title })).toBeInTheDocument();
    expect(screen.getByText('Child route content')).toBeInTheDocument();
  });

  it('masks unknown and inaccessible cases without rendering child fixture content', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'resource not found' }, 404));

    renderWithQuery(
      <CaseShell caseId="b4ab65f9-f6bc-46f0-94df-792892b90b83">
        <p>Should never render</p>
      </CaseShell>,
    );

    expect(await screen.findByText('Case unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Should never render')).not.toBeInTheDocument();
  });
});
