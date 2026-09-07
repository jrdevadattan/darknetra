import type { Case, CaseDigest, Chat, ExecutionSnapshot, Page, RunRef, Thread, ThreadMessage, User } from "@/lib/types";

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code?: string, message = "Request failed") {
    super(message);
    this.name = "ApiError";
  }
}

function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie.split("; ").find((cookie) => cookie.startsWith("darknetra_csrf="))?.split("=").slice(1).join("=");
}

export function buildRequest(method: string, body?: unknown, csrf = csrfToken()): RequestInit {
  const mutation = !["GET", "HEAD", "OPTIONS"].includes(method);
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (mutation && csrf) headers["X-CSRF-Token"] = csrf;
  return { method, headers, credentials: "include", body: body === undefined ? undefined : JSON.stringify(body) };
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, buildRequest(method, body));
  } catch {
    throw new ApiError(0, "NETWORK_REQUIRED", "DARKNETRA is unavailable. Check the API connection and try again.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { error?: { code?: string; message?: string }; detail?: string };
    throw new ApiError(response.status, payload.error?.code, payload.error?.message ?? payload.detail ?? "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/v1/health/ready"),
  me: () => request<User>("/api/v1/auth/me"),
  login: (username: string, password: string) => request<User>("/api/v1/auth/login", "POST", { username, password }),
  logout: () => request<void>("/api/v1/auth/logout", "POST"),
  cases: () => request<Page<Case>>("/api/v1/cases"),
  caseDigest: (caseId: string) => request<CaseDigest>(`/api/v1/cases/${caseId}/digest`),
  chats: () => request<Page<Chat>>("/api/v1/chats"),
  threads: (caseId: string) => request<Page<Thread>>(`/api/v1/cases/${caseId}/threads`),
  messages: (caseId: string, threadId: string) => request<Page<ThreadMessage>>(`/api/v1/cases/${caseId}/threads/${threadId}/messages`),
  postMessage: (caseId: string, threadId: string, content: string) =>
    request<RunRef>(`/api/v1/cases/${caseId}/threads/${threadId}/messages`, "POST", { content }),
  execution: (caseId: string, threadId: string, runId: string) =>
    request<ExecutionSnapshot>(`/api/v1/cases/${caseId}/threads/${threadId}/runs/${runId}/execution`),
  cancelRun: (caseId: string, threadId: string, runId: string) =>
    request<void>(`/api/v1/cases/${caseId}/threads/${threadId}/runs/${runId}/cancel`, "POST"),
};
