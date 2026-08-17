import { afterEach, describe, expect, it, vi } from "vitest";

import { HealthApiError, fetchHealth } from "./health";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("fetchHealth", () => {
  it("returns a validated ready response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: "ready",
          version: "test-build",
          components: [{ name: "api", status: "ready" }],
        }),
      }),
    );

    await expect(fetchHealth()).resolves.toEqual({
      status: "ready",
      version: "test-build",
      components: [{ name: "api", status: "ready" }],
    });
  });

  it("throws a typed http error for non-2xx responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    await expect(fetchHealth()).rejects.toMatchObject<HealthApiError>({ kind: "http", status: 503 });
  });

  it("throws a typed network error when fetch rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("connection refused")));
    await expect(fetchHealth()).rejects.toMatchObject<HealthApiError>({ kind: "network" });
  });
});
