'use client';

import type { ReactNode } from 'react';
import { useEffect } from 'react';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

import { AsyncState } from '@/components/darknetra/async-state';
import {
  getCurrentUser,
  logout,
  refreshSession,
  type AuthUser,
} from '@/lib/api/auth';
import { ApiError } from '@/lib/api/errors';
import { queryKeys } from '@/lib/query/keys';

async function loadCurrentSession(): Promise<AuthUser> {
  try {
    return await getCurrentUser();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      const refreshed = await refreshSession();
      return refreshed.user;
    }
    throw error;
  }
}

export function useAuthSession() {
  return useQuery({
    queryKey: queryKeys.auth.me,
    queryFn: loadCurrentSession,
    retry: false,
    staleTime: 30_000,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.clear();
      router.replace('/auth/v2/login');
      router.refresh();
    },
  });
}

export function SessionGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const session = useAuthSession();
  const user = session.data;
  const unauthenticated = session.error instanceof ApiError && session.error.status === 401;

  useEffect(() => {
    if (unauthenticated) {
      router.replace('/auth/v2/login');
      return;
    }
    if (user?.must_change_password) {
      router.replace('/auth/v2/change-password');
    }
  }, [router, unauthenticated, user?.must_change_password]);

  if (session.isPending) {
    return <AsyncState state="loading" />;
  }

  if (unauthenticated || user?.must_change_password) {
    return <AsyncState state="loading" />;
  }

  if (session.isError) {
    if (session.error instanceof ApiError && session.error.status === 0) {
      return (
        <AsyncState
          state="offline"
          title="Authentication service unavailable"
          description="The authenticated session could not be verified because the API is unreachable."
        />
      );
    }

    return (
      <AsyncState
        state="error"
        title="Unable to verify session"
        description="The authenticated session could not be verified."
      />
    );
  }

  return <>{children}</>;
}
