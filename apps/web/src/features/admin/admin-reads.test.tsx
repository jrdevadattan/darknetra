import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { RolePermissionMatrix } from './roles/role-permission-matrix';
import { UserTable } from './users/user-table';

const fetchMock = vi.fn();

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
      mutations: { retry: false },
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

describe('RolePermissionMatrix', () => {
  it('renders the exact permission truth returned by the backend instead of a frontend matrix', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        roles: [
          {
            role: 'ANALYST',
            permissions: ['CASE_READ', 'SERVER_ONLY_POLICY_CHANGE'],
          },
          {
            role: 'AUDITOR',
            permissions: ['AUDIT_READ'],
          },
        ],
      }),
    );

    renderWithQuery(<RolePermissionMatrix />);

    expect(await screen.findByText('SERVER_ONLY_POLICY_CHANGE')).toBeInTheDocument();
    expect(screen.getByText('CASE_READ')).toBeInTheDocument();
    expect(screen.getByText('AUDIT_READ')).toBeInTheDocument();
    expect(screen.queryByText('Scoped')).not.toBeInTheDocument();
  });

  it('renders a clear access-denied state for a 403 policy response', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'permission denied' }, 403));

    renderWithQuery(<RolePermissionMatrix />);

    expect(await screen.findByText('Role administration access denied')).toBeInTheDocument();
  });
});

describe('UserTable', () => {
  it('renders only safe user fields even if an unexpected response contains sensitive-looking extras', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        items: [
          {
            id: 'f11eed63-48d9-41f3-9149-c4d45b98bda9',
            username: 'analyst.one',
            display_name: 'Analyst One',
            is_active: true,
            global_roles: ['ANALYST'],
            password_hash: 'DO-NOT-RENDER-PASSWORD-HASH',
            refresh_token_hash: 'DO-NOT-RENDER-TOKEN-HASH',
            failed_login_count: 5,
            locked_until: '2099-01-01T00:00:00Z',
          },
        ],
      }),
    );

    renderWithQuery(<UserTable />);

    expect(await screen.findByText('Analyst One')).toBeInTheDocument();
    expect(screen.getByText('analyst.one')).toBeInTheDocument();
    expect(screen.getByText('ANALYST')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.queryByText('DO-NOT-RENDER-PASSWORD-HASH')).not.toBeInTheDocument();
    expect(screen.queryByText('DO-NOT-RENDER-TOKEN-HASH')).not.toBeInTheDocument();
    expect(screen.queryByText('2099-01-01T00:00:00Z')).not.toBeInTheDocument();
    expect(screen.queryByText('5')).not.toBeInTheDocument();
  });

  it('renders an explicit unavailable state instead of a blank table on 404', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'resource not found' }, 404));

    renderWithQuery(<UserTable />);

    expect(await screen.findByText('User directory unavailable')).toBeInTheDocument();
  });
});
