"use client";

import {
  useInfiniteQuery,
  useQuery,
  type QueryClient,
} from "@tanstack/react-query";
import type { Page } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export function csrfToken(
  cookie = typeof document === "undefined" ? "" : document.cookie,
) {
  return cookie
    .split(";")
    .map((v) => v.trim())
    .find((v) => v.startsWith("darknetra_csrf="))
    ?.slice(15);
}
export function requestOptions(method: string, body?: unknown): RequestInit {
  const headers = new Headers({ Accept: "application/json" });
  if (!["GET", "HEAD"].includes(method)) {
    const csrf = csrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const form = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !form)
    headers.set("Content-Type", "application/json");
  return {
    method,
    headers,
    credentials: "include",
    cache: "no-store",
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  };
}
let refreshPromise: Promise<boolean> | null = null;
export const SESSION_EXPIRED = "darknetra:session-expired";
async function refresh() {
  if (!refreshPromise)
    refreshPromise = fetch("/api/v1/auth/refresh", requestOptions("POST"))
      .then(async (response) => {
        if (response.ok) return true;
        if (response.status === 401 || response.status === 403) return false;
        throw await readError(response);
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError) throw error;
        throw new ApiError(
          0,
          "NETWORK_REQUIRED",
          "Session refresh is temporarily unavailable. Check the connection and retry.",
        );
      })
      .finally(() => {
        refreshPromise = null;
      });
  return refreshPromise;
}
export async function authorizedFetch(path: string, options: RequestInit = {}) {
  const sessionEndpoint = path === "/auth/login" || path === "/auth/refresh";
  let response = await fetch("/api/v1" + path, {
    credentials: "include",
    cache: "no-store",
    ...options,
  });
  if (response.status === 401 && !sessionEndpoint && (await refresh())) {
    const headers = new Headers(options.headers);
    if (options.method && options.method !== "GET") {
      const csrf = csrfToken();
      if (csrf) headers.set("X-CSRF-Token", csrf);
    }
    response = await fetch("/api/v1" + path, {
      credentials: "include",
      cache: "no-store",
      ...options,
      headers,
    });
  }
  if (
    response.status === 401 &&
    !sessionEndpoint &&
    !options.signal?.aborted &&
    typeof window !== "undefined"
  ) {
    window.dispatchEvent(new Event(SESSION_EXPIRED));
  }
  return response;
}
export async function readError(response: Response) {
  const data = await response.json().catch(() => ({}));
  const message =
    data.error?.message ??
    (typeof data.detail === "string"
      ? data.detail
      : "The request could not be completed.");
  return new ApiError(
    response.status,
    data.error?.code ?? "REQUEST_FAILED",
    message,
    data.error?.request_id,
  );
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    const options = { ...requestOptions(method, body), signal };
    if (path === "/auth/me") {
      response = await fetch("/api/v1" + path, options);
      if (response.status === 401 && (await refresh()))
        response = await fetch("/api/v1" + path, options);
    } else response = await authorizedFetch(path, options);
  } catch (error) {
    if (signal?.aborted || error instanceof ApiError) throw error;
    throw new ApiError(
      0,
      "NETWORK_REQUIRED",
      "Unable to reach DARKNETRA. Check the connection and try again.",
    );
  }
  if (!response.ok) throw await readError(response);
  const text = await response.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}
export function useApi<T>(
  path: string | null,
  interval?: number | ((data: T | undefined) => number | false),
) {
  return useQuery<T, ApiError>({
    queryKey: ["api", path],
    enabled: Boolean(path),
    queryFn: ({ signal }) => api<T>(path!, "GET", undefined, signal),
    staleTime: 10_000,
    retry: false,
    refetchInterval:
      typeof interval === "function"
        ? (query) => interval(query.state.data)
        : interval,
  });
}
export function usePaged<T>(path: string | null, interval?: number) {
  const query = useInfiniteQuery<Page<T>, ApiError>({
    queryKey: ["api", path, "pages"],
    enabled: Boolean(path),
    initialPageParam: "",
    queryFn: ({ pageParam, signal }) =>
      api<Page<T>>(
        path! +
          (path!.includes("?") ? "&" : "?") +
          "limit=50" +
          (pageParam ? "&cursor=" + encodeURIComponent(String(pageParam)) : ""),
        "GET",
        undefined,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
    refetchInterval: interval,
    retry: false,
  });
  return {
    ...query,
    items: query.data?.pages.flatMap((p) => p.items) ?? [],
    total: query.data?.pages[0]?.total,
  };
}
export function invalidateCase(client: QueryClient, id: string) {
  return client.invalidateQueries({
    predicate: (query) =>
      query.queryKey[0] === "api" &&
      String(query.queryKey[1]).startsWith("/cases/" + id),
  });
}
export async function download(path: string, filename: string) {
  const response = await authorizedFetch(path);
  if (!response.ok) throw await readError(response);
  const href = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(href), 30_000);
}
