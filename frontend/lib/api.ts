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

export async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
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

export type SseFrame = { id?: string; event: string; data: unknown };

export function parseSseFrames(text: string): SseFrame[] {
  return text.split(/\r?\n\r?\n/).flatMap((frame) => {
    const values = Object.fromEntries(frame.split(/\r?\n/).flatMap((line) => {
      const match = /^(id|event|data):\s?(.*)$/.exec(line);
      return match ? [[match[1], match[2]]] : [];
    }));
    if (!values.data) return [];
    try { return [{ id: values.id, event: values.event ?? "message", data: JSON.parse(values.data) }]; } catch { return []; }
  });
}

async function stream(path: string, lastEventId: number, onFrame: (frame: SseFrame) => void, signal: AbortSignal) {
  const response = await fetch(path, { headers: { "Last-Event-ID": String(lastEventId) }, credentials: "include", signal });
  if (!response.ok || !response.body) throw new ApiError(response.status, undefined, "Run-event connection failed");
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
  while (!signal.aborted) {
    const next = await reader.read(); if (next.done) break;
    buffer += decoder.decode(next.value, { stream: true });
    const cut = buffer.lastIndexOf("\n\n");
    if (cut < 0) continue;
    const complete = buffer.slice(0, cut + 2); buffer = buffer.slice(cut + 2);
    parseSseFrames(complete).forEach(onFrame);
  }
}

export const api = {
  health: () => request<{ status: string }>("/api/v1/health/ready"),
  me: () => request<User>("/api/v1/auth/me"),
  login: (username: string, password: string) => request<User>("/api/v1/auth/login", "POST", { username, password }),
  logout: () => request<void>("/api/v1/auth/logout", "POST"),
  cases: () => request<Page<Case>>("/api/v1/cases"),
  caseDigest: (caseId: string) => request<CaseDigest>(`/api/v1/cases/${caseId}/digest`),
  createCase: (body: unknown) => request<Case>("/api/v1/cases", "POST", body),
  summary: (caseId: string) => request<Record<string, unknown>>(`/api/v1/cases/${caseId}/summary`),
  panel: (caseId: string, path: string) => request<Record<string, unknown>>(`/api/v1/cases/${caseId}/${path}`),
  createThread: (caseId: string, body: unknown) => request<Thread>(`/api/v1/cases/${caseId}/threads`, "POST", body),
  createChat: (body: unknown) => request<Chat>("/api/v1/chats", "POST", body),
  createWatchlist: (caseId: string, name: string) => request<Record<string, unknown>>(`/api/v1/cases/${caseId}/watchlists`, "POST", { name }),
  createWatchlistItem: (caseId: string, watchlistId: string, body: unknown) => request<Record<string, unknown>>(`/api/v1/cases/${caseId}/watchlists/${watchlistId}/items`, "POST", body),
  plugins: (caseId: string) => request<Record<string, unknown>>(`/api/v1/cases/${caseId}/plugins`),
  tools: () => request<Record<string, unknown>>("/api/v1/tools"),
  chats: () => request<Page<Chat>>("/api/v1/chats"),
  threads: (caseId: string) => request<Page<Thread>>(`/api/v1/cases/${caseId}/threads`),
  messages: (caseId: string, threadId: string) => request<Page<ThreadMessage>>(`/api/v1/cases/${caseId}/threads/${threadId}/messages`),
  postMessage: (caseId: string, threadId: string, content: string) =>
    request<RunRef>(`/api/v1/cases/${caseId}/threads/${threadId}/messages`, "POST", { content }),
  execution: (caseId: string, threadId: string, runId: string) =>
    request<ExecutionSnapshot>(`/api/v1/cases/${caseId}/threads/${threadId}/runs/${runId}/execution`),
  cancelRun: (caseId: string, threadId: string, runId: string) =>
    request<void>(`/api/v1/cases/${caseId}/threads/${threadId}/runs/${runId}/cancel`, "POST"),
  subscribeRunEvents: (caseId: string, threadId: string, runId: string, lastEventId: number, onFrame: (frame: SseFrame) => void, signal: AbortSignal) =>
    stream(`/api/v1/cases/${caseId}/threads/${threadId}/runs/${runId}/events`, lastEventId, onFrame, signal),
};
