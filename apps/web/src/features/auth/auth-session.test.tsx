import type { ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { queryKeys } from '@/lib/query/keys';

import { ChangePasswordForm } from './change-password-form';
import { LoginForm } from './login-form';
import { SessionControls } from './session-controls';
import { SessionGate } from './session-gate';

const navigation = vi.hoisted(() => ({
  replace: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
  useRouter: () => navigation,
}));

const fetchMock = vi.fn();

const AUTH_USER = {
  id: '2b18f363-8fc0-44aa-8312-7f4792e663af',
  username: 'investigator',
  display_name: 'Investigator One',
  global_roles: ['ANALYST'] as const,
  must_change_password: false,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function renderWithQuery(ui: ReactNode, queryClient?: QueryClient) {
  const client =
    queryClient ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  return {
    queryClient: client,
    ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>),
  };
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  navigation.replace.mockReset();
  navigation.refresh.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('LoginForm', () => {
  it('uses investigator credential semantics, supports keyboard submit, and clears the password', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ user: AUTH_USER }));
    const user = userEvent.setup();

    renderWithQuery(<LoginForm />);

    const username = screen.getByLabelText('Username');
    const password = screen.getByLabelText('Password');
    expect(username).toHaveAttribute('autocomplete', 'username');
    expect(password).toHaveAttribute('autocomplete', 'current-password');

    await user.type(username, 'investigator');
    await user.type(password, 'Synthetic-Only-Password-42!');
    await user.keyboard('{Enter}');

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith('/dashboard'));
    expect(password).toHaveValue('');
  });

  it('shows a generic credential failure and never echoes the backend auth detail', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'invalid credentials or session' }, 401));
    const user = userEvent.setup();

    renderWithQuery(<LoginForm />);

    await user.type(screen.getByLabelText('Username'), 'investigator');
    const password = screen.getByLabelText('Password');
    await user.type(password, 'wrong-password');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Unable to sign in with those credentials.')).toBeInTheDocument();
    expect(screen.queryByText('invalid credentials or session')).not.toBeInTheDocument();
    expect(password).toHaveValue('');
  });

  it('disables submission while login is in flight and routes forced-change users correctly', async () => {
    let resolveRequest: ((response: Response) => void) | undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveRequest = resolve;
        }),
    );
    const user = userEvent.setup();

    renderWithQuery(<LoginForm />);

    await user.type(screen.getByLabelText('Username'), 'bootstrap');
    await user.type(screen.getByLabelText('Password'), 'Temporary-Password-42!');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByRole('button', { name: 'Signing in…' })).toBeDisabled();

    resolveRequest?.(
      jsonResponse({
        user: {
          ...AUTH_USER,
          username: 'bootstrap',
          must_change_password: true,
        },
      }),
    );

    await waitFor(() =>
      expect(navigation.replace).toHaveBeenCalledWith('/auth/v2/change-password'),
    );
  });
});

describe('ChangePasswordForm', () => {
  it('uses new-password autocomplete, clears values, and returns the user to the dashboard', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(AUTH_USER));
    const user = userEvent.setup();

    renderWithQuery(<ChangePasswordForm />);

    const newPassword = screen.getByLabelText('New password');
    const confirmPassword = screen.getByLabelText('Confirm new password');
    expect(newPassword).toHaveAttribute('autocomplete', 'new-password');
    expect(confirmPassword).toHaveAttribute('autocomplete', 'new-password');
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument();

    await user.type(newPassword, 'Replacement-Password-42!');
    await user.type(confirmPassword, 'Replacement-Password-42!');
    await user.click(screen.getByRole('button', { name: 'Update password' }));

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith('/dashboard'));
    expect(newPassword).toHaveValue('');
    expect(confirmPassword).toHaveValue('');
  });
});

describe('SessionGate', () => {
  it('shows the checking state while the current-user request is pending', () => {
    fetchMock.mockImplementationOnce(() => new Promise<Response>(() => undefined));

    renderWithQuery(
      <SessionGate>
        <p>Protected content</p>
      </SessionGate>,
    );

    expect(screen.getByTestId('async-state-loading')).toBeInTheDocument();
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });

  it('renders protected content for an authenticated user', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(AUTH_USER));

    renderWithQuery(
      <SessionGate>
        <p>Protected content</p>
      </SessionGate>,
    );

    expect(await screen.findByText('Protected content')).toBeInTheDocument();
  });

  it('routes a forced-change session away from the normal shell', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ ...AUTH_USER, must_change_password: true }),
    );

    renderWithQuery(
      <SessionGate>
        <p>Protected content</p>
      </SessionGate>,
    );

    await waitFor(() =>
      expect(navigation.replace).toHaveBeenCalledWith('/auth/v2/change-password'),
    );
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });

  it('tries refresh once and then routes an unauthenticated session to login', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: 'invalid credentials or session' }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: 'invalid credentials or session' }, 401));

    renderWithQuery(
      <SessionGate>
        <p>Protected content</p>
      </SessionGate>,
    );

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith('/auth/v2/login'));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('shows backend-unavailable instead of redirecting when the API cannot be reached', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('network unavailable'));

    renderWithQuery(
      <SessionGate>
        <p>Protected content</p>
      </SessionGate>,
    );

    expect(await screen.findByText('Authentication service unavailable')).toBeInTheDocument();
    expect(navigation.replace).not.toHaveBeenCalled();
  });
});

describe('SessionControls', () => {
  it('clears all cached investigation data before redirecting after successful logout', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: 60_000 },
        mutations: { retry: false },
      },
    });
    queryClient.setQueryData(queryKeys.auth.me, AUTH_USER);
    queryClient.setQueryData(['cases', 'list', {}], { items: ['sensitive cached case'] });
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const user = userEvent.setup();

    renderWithQuery(<SessionControls />, queryClient);

    expect(screen.getByText('Investigator One')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Sign out' }));

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith('/auth/v2/login'));
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });
});
