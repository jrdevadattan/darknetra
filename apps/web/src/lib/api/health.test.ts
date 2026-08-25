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

  it("accepts additional ready components from the API health contract", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          status: "ready",
          version: "test-build",
          components: [
            { name: "api", status: "ready" },
            { name: "sensitive-field-crypto", status: "ready" },
          ],
        }),
      }),
    );

    await expect(fetchHealth()).resolves.toEqual({
      status: "ready",
      version: "test-build",
      components: [
        { name: "api", status: "ready" },
        { name: "sensitive-field-crypto", status: "ready" },
      ],
    });
  });

  it("throws a typed http error for non-2xx responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));

    try {
      await fetchHealth();
      throw new Error("Expected fetchHealth to reject");
    } catch (error) {
      expect(error).toBeInstanceOf(HealthApiError);
      expect(error).toMatchObject({ kind: "http", status: 503 });
    }
  });

  it("throws a typed network error when fetch rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("connection refused")));

    try {
      await fetchHealth();
      throw new Error("Expected fetchHealth to reject");
    } catch (error) {
      expect(error).toBeInstanceOf(HealthApiError);
      expect(error).toMatchObject({ kind: "network" });
    }
  });
});
