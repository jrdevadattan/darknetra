import { ApiError, defaultApiErrorCode } from "@/lib/api/errors";

const CSRF_COOKIE = "darknetra_csrf";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function apiBaseUrl(): string {
  return (
    process.env.DARKNETRA_API_BASE_URL ??
    process.env.NEXT_PUBLIC_DARKNETRA_API_BASE_URL ??
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${apiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const prefix = `${encodeURIComponent(name)}=`;
  for (const entry of document.cookie.split(";")) {
    const value = entry.trim();
    if (value.startsWith(prefix)) {
      return decodeURIComponent(value.slice(prefix.length));
    }
  }
  return undefined;
}

function errorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (typeof record.detail === "string") return record.detail;
  }
  return `DARKNETRA API request failed with HTTP ${status}.`;
}

function errorCode(payload: unknown, status: number): string {
  if (payload && typeof payload === "object") {
    const code = (payload as Record<string, unknown>).code;
    if (typeof code === "string" && code.length > 0) return code;
  }
  return defaultApiErrorCode(status);
}

async function readResponsePayload(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  return text || undefined;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);

  if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (!SAFE_METHODS.has(method)) {
    const csrfToken = readCookie(CSRF_COOKIE);
    if (csrfToken && !headers.has("X-CSRF-Token")) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }

  let response: Response;
  try {
    response = await fetch(resolveApiUrl(path), {
      ...init,
      method,
      headers,
      credentials: "include",
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw new ApiError({
        status: 0,
        code: "REQUEST_ABORTED",
        message: "DARKNETRA API request was aborted.",
        cause,
      });
    }
    throw new ApiError({
      status: 0,
      code: "NETWORK_ERROR",
      message: cause instanceof Error ? cause.message : "DARKNETRA API is unreachable.",
      cause,
    });
  }

  const payload = await readResponsePayload(response);
  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      code: errorCode(payload, response.status),
      message: errorMessage(payload, response.status),
      details: payload,
    });
  }
  return payload as T;
}
