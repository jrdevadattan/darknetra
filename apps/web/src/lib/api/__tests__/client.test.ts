import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  document.cookie = "darknetra_csrf=; Max-Age=0; Path=/";
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("returns parsed JSON and always includes browser credentials", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));

    await expect(apiFetch<{ ok: boolean }>("/api/v1/health")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: "include" });
  });

  it.each([
    [401, "UNAUTHORIZED"],
    [403, "FORBIDDEN"],
    [404, "NOT_FOUND"],
  ])("maps %s responses to typed errors", async (status, code) => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "denied" }, status));

    const error = await apiFetch("/api/v1/resource").catch((cause) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status, code, details: { detail: "denied" } });
  });

  it("preserves structured 422 validation details", async () => {
    const details = {
      detail: [{ type: "string_pattern_mismatch", loc: ["body", "case_code"], msg: "invalid" }],
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(details, 422));

    const error = await apiFetch("/api/v1/cases", { method: "POST" }).catch((cause) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, code: "VALIDATION_ERROR", details });
  });

  it("maps server errors without string matching at call sites", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "temporary failure" }, 503));

    const error = await apiFetch("/api/v1/cases").catch((cause) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, code: "SERVER_ERROR" });
  });

  it("maps network failures to a typed network error", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    const error = await apiFetch("/api/v1/cases").catch((cause) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, code: "NETWORK_ERROR" });
  });

  it("maps aborted requests distinctly", async () => {
    fetchMock.mockRejectedValueOnce(new DOMException("The operation was aborted", "AbortError"));

    const error = await apiFetch("/api/v1/cases", { signal: new AbortController().signal }).catch(
      (cause) => cause,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 0, code: "REQUEST_ABORTED" });
  });

  it("reads the non-HttpOnly CSRF cookie and sends it on mutations", async () => {
    document.cookie = "darknetra_csrf=csrf-token-123; Path=/";
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "case-1" }, 201));

    await apiFetch("/api/v1/cases", {
      method: "POST",
      body: JSON.stringify({ case_code: "CHD-001" }),
    });

    const request = fetchMock.mock.calls[0]?.[1];
    const headers = new Headers(request?.headers);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-token-123");
    expect(headers.get("Content-Type")).toBe("application/json");
  });
});
