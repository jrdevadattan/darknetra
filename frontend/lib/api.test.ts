import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api,
  authorizedFetch,
  csrfToken,
  requestOptions,
  SESSION_EXPIRED,
} from "./api";
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
describe("authenticated API client", () => {
  it("reads only the exact CSRF cookie and includes it on mutations", () => {
    expect(csrfToken("other=1; darknetra_csrf=abc123; extra=2")).toBe("abc123");
    expect(csrfToken("not_darknetra_csrf=secret")).toBeUndefined();
    vi.stubGlobal("document", { cookie: "darknetra_csrf=abc123" });
    expect(
      new Headers(requestOptions("POST", {}).headers).get("x-csrf-token"),
    ).toBe("abc123");
    expect(new Headers(requestOptions("GET").headers).has("x-csrf-token")).toBe(
      false,
    );
  });
  it("lets the browser supply multipart boundaries", () => {
    const form = new FormData();
    form.set("file", new Blob(["SYNTHETIC"]), "synthetic.txt");
    const options = requestOptions("POST", form);
    expect(options.body).toBe(form);
    expect(new Headers(options.headers).has("content-type")).toBe(false);
  });
  it("accepts empty mutation responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    expect(await api("/auth/logout", "POST")).toBeUndefined();
  });
  it("preserves stable errors and request IDs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          {
            error: {
              code: "POLICY_DENIED",
              message: "Case policy denies this action",
              request_id: "SYN-REQUEST",
            },
          },
          { status: 403 },
        ),
      ),
    );
    await expect(api("/cases/synthetic")).rejects.toMatchObject({
      status: 403,
      code: "POLICY_DENIED",
      requestId: "SYN-REQUEST",
    });
  });
  it("refreshes concurrent expired sessions once and uses the rotated CSRF token", async () => {
    const doc = { cookie: "darknetra_csrf=old" };
    vi.stubGlobal("document", doc);
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let calls = 0;
    const fetcher = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) {
        await gate;
        doc.cookie = "darknetra_csrf=new";
        return Response.json({});
      }
      calls++;
      if (calls <= 2) return new Response(null, { status: 401 });
      expect(new Headers(options?.headers).get("x-csrf-token")).toBe("new");
      return Response.json({ ok: true });
    });
    vi.stubGlobal("fetch", fetcher);
    const first = authorizedFetch("/cases/a", requestOptions("PATCH", {})),
      second = authorizedFetch("/cases/b", requestOptions("PATCH", {}));
    await new Promise((resolve) => setTimeout(resolve, 0));
    release();
    expect((await Promise.all([first, second])).every((r) => r.ok)).toBe(true);
    expect(
      fetcher.mock.calls.filter(([url]) => url.endsWith("/auth/refresh")),
    ).toHaveLength(1);
  });
  it("reports network failure without retrying a mutation", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    vi.stubGlobal("fetch", fetcher);
    await expect(api("/cases", "POST", {})).rejects.toMatchObject({
      code: "NETWORK_REQUIRED",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("refreshes an expired access session for authenticated account actions", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(Response.json({}))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);
    await api("/auth/logout", "POST");
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/auth/logout",
      "/api/v1/auth/refresh",
      "/api/v1/auth/logout",
    ]);
  });
  it("expires the workspace after refresh is rejected but leaves login errors local", async () => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal("window", { dispatchEvent });
    const fetcher = vi
      .fn()
      .mockImplementation(async () => new Response(null, { status: 401 }));
    vi.stubGlobal("fetch", fetcher);
    await authorizedFetch("/auth/tokens");
    expect(dispatchEvent).toHaveBeenCalledTimes(1);
    expect(dispatchEvent.mock.calls[0][0].type).toBe(SESSION_EXPIRED);
    dispatchEvent.mockClear();
    fetcher.mockClear();
    await authorizedFetch("/auth/login", requestOptions("POST", {}));
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(dispatchEvent).not.toHaveBeenCalled();
  });
  it.each(["network", "server"])(
    "preserves cached authentication on a %s refresh outage",
    async (failure) => {
      const dispatchEvent = vi.fn();
      vi.stubGlobal("window", { dispatchEvent });
      const fetcher = vi
        .fn()
        .mockResolvedValueOnce(new Response(null, { status: 401 }));
      if (failure === "network")
        fetcher.mockRejectedValueOnce(new TypeError("fetch failed"));
      else
        fetcher.mockResolvedValueOnce(
          Response.json(
            {
              error: {
                code: "NETWORK_REQUIRED",
                message: "Temporarily unavailable",
              },
            },
            { status: 503 },
          ),
        );
      vi.stubGlobal("fetch", fetcher);
      await expect(api("/auth/tokens")).rejects.toMatchObject({
        code: "NETWORK_REQUIRED",
        status: failure === "network" ? 0 : 503,
      });
      expect(dispatchEvent).not.toHaveBeenCalled();
    },
  );
});
