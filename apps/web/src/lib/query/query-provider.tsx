"use client";

import type { ReactNode } from "react";
import { useState } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";

function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false;
  if (!(error instanceof ApiError)) return failureCount < 1;
  if (error.code === "REQUEST_ABORTED") return false;
  if ([401, 403, 404, 422].includes(error.status)) return false;
  return error.status === 0 || error.status >= 500;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: shouldRetry,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function QueryProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [queryClient] = useState(createQueryClient);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
