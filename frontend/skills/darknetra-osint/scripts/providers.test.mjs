import { test, expect } from "vitest";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { EventEmitter } from "node:events";
import {
  integrationStatus,
  normalizeProvider,
  providerJson,
  providerLookup,
} from "./providers.mjs";

const key = "SYNTHETIC-private-token";
async function withConfig(values, run) {
  const dir = await mkdtemp(
    path.join(tmpdir(), "darknetra-SYNTHETIC-providers-"),
  );
  const file = path.join(dir, "providers.json");
  try {
    if (values !== null) await writeFile(file, JSON.stringify(values));
    await run({ DARKNETRA_PROVIDER_FILE: file });
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}
test("missing keys do not make requests; status never exposes credential values or claims connection", async () => {
  await withConfig(null, async (env) => {
    const status = await integrationStatus(env);
    expect(
      status.providers.every((p) => p.state === "credentials_required"),
    ).toBe(true);
    let called = false;
    await expect(
      providerLookup("flashpoint", "example.com", "1", {
        env,
        request: async () => {
          called = true;
        },
      }),
    ).rejects.toMatchObject({ code: "AUTH_REQUIRED" });
    expect(called).toBe(false);
  });
  await withConfig({ flashpoint: key }, async (env) => {
    const status = await integrationStatus(env);
    expect(status.providers[0].state).toBe("configured_unverified");
    expect(JSON.stringify(status)).not.toContain(key);
  });
  await withConfig({ flashpoint: 42 }, async (env) => {
    expect(
      (await integrationStatus(env)).providers.every(
        (p) => p.state === "configuration_error",
      ),
    ).toBe(true);
  });
});
test("provider requests encode selectors and only return bounded assessment fields", async () => {
  await withConfig(
    { flashpoint: key, "recorded-future": key, chainalysis: key },
    async (env) => {
      const requests = [];
      const request = async (provider, url, token) => {
        requests.push({ provider, url, token });
        if (provider === "flashpoint")
          return {
            items: [
              {
                id: "SYNTHETIC-id",
                value: "example.com",
                type: "domain",
                score: { value: "SYNTHETIC-assessment" },
                secret: key,
              },
            ],
          };
        if (provider === "recorded-future")
          return {
            data: {
              entity: { id: "idn:example.com", name: "SYNTHETIC domain" },
              risk: { score: 0, evidenceDetails: [] },
            },
          };
        return { identifications: [] };
      };
      const fp = await providerLookup(
        "flashpoint",
        "https://example.com/?a=1&b=2",
        "1",
        { env, request },
      );
      expect(new URL(requests[0].url).searchParams.get("ioc_value")).toBe(
        "https://example.com/?a=1&b=2",
      );
      expect(new URL(requests[0].url).searchParams.get("size")).toBe("1");
      expect(JSON.stringify(fp)).not.toContain(key);
      const rf = await providerLookup(
        "recorded-future",
        "example.com",
        undefined,
        { env, request },
      );
      expect(requests[1].url).toContain("/domain/idn%3Aexample.com");
      expect(rf.riskScore).toBe(0);
      const ca = await providerLookup(
        "chainalysis",
        "SYNTHETIC00000000000000000000000000000000",
        undefined,
        { env, request },
      );
      expect(ca.identifications).toEqual([]);
      expect(ca.text).toContain("not a clean-wallet determination");
      expect(ca.scope).toContain("No Reactor tracing");
      expect(
        requests.every((r) => r.token === key && !r.url.includes(key)),
      ).toBe(true);
      await expect(
        providerLookup("recorded-future", "127.0.0.1", undefined, {
          env,
          request,
        }),
      ).rejects.toMatchObject({ code: "VALIDATION" });
      await expect(
        providerLookup(
          "flashpoint",
          "https://user:pass@example.com/",
          undefined,
          { env, request },
        ),
      ).rejects.toMatchObject({ code: "VALIDATION" });
      await expect(
        providerLookup("chainalysis", "../../../secrets", undefined, {
          env,
          request,
        }),
      ).rejects.toMatchObject({ code: "VALIDATION" });
      expect(requests).toHaveLength(3);
    },
  );
});
test("malformed or error payloads are never empty successful provider checks", () => {
  for (const provider of ["flashpoint", "recorded-future", "chainalysis"])
    expect(() =>
      normalizeProvider(
        provider,
        { message: "SYNTHETIC denied", error: key },
        "SYNTHETIC",
        "https://example.com/",
      ),
    ).toThrow();
  const records = Array.from({ length: 20 }, (_, i) => ({
    id: `SYNTHETIC-${i}`,
    value: "example.com",
  }));
  const result = normalizeProvider(
    "flashpoint",
    { items: records },
    "example.com",
    "https://example.com/",
    2,
  );
  expect(result.records).toHaveLength(2);
  expect(result.truncated).toBe(true);
});
test("credentials cannot follow arbitrary endpoints or private DNS destinations", async () => {
  let called = false;
  const transport = {
    get: () => {
      called = true;
    },
    lookup: async () => [{ address: "127.0.0.1", family: 4 }],
  };
  await expect(
    providerJson(
      "flashpoint",
      "https://example.com/technical-intelligence/v2/indicators",
      key,
      transport,
    ),
  ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  await expect(
    providerJson(
      "flashpoint",
      "https://api.flashpoint.io/unrelated",
      key,
      transport,
    ),
  ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  await expect(
    providerJson(
      "flashpoint",
      "https://api.flashpoint.io/technical-intelligence/v2/indicators",
      key,
      transport,
    ),
  ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  expect(called).toBe(false);
});

test("GET transport handles auth, entitlement, redirects, limits and bad payloads without leaking secrets", async () => {
  // Transport is fully synthetic: the DNS answer never opens a socket.
  function mock(status, body = key, contentType = "application/json") {
    const calls = [];
    return {
      calls,
      lookup: async () => [{ address: "93.184.216.34", family: 4 }],
      get: (url, options, callback) => {
        calls.push({ url, options });
        const request = new EventEmitter();
        request.destroy = (error) => request.emit("error", error);
        setImmediate(() => {
          const response = new EventEmitter();
          response.statusCode = status;
          response.headers = {
            "content-type": contentType,
            location: "https://example.com/SYNTHETIC",
          };
          response.resume = () => {};
          callback(response);
          response.emit("data", Buffer.from(body));
          response.emit("end");
        });
        return request;
      },
    };
  }
  const url =
    "https://api.flashpoint.io/technical-intelligence/v2/indicators?ioc_value=example.com&size=1";
  for (const [status, code] of [
    [401, "AUTH_REQUIRED"],
    [403, "ACCESS_DENIED"],
    [429, "RATE_LIMITED"],
    [302, "UPSTREAM_UNAVAILABLE"],
    [404, "NOT_FOUND"],
  ]) {
    const transport = mock(status);
    let caught;
    try {
      await providerJson("flashpoint", url, key, transport);
    } catch (error) {
      caught = error;
    }
    expect(caught.code).toBe(code);
    expect(caught.message).not.toContain(key);
    expect(transport.calls).toHaveLength(1);
  }
  const transport = mock(200, '{"items":[]}');
  expect(await providerJson("flashpoint", url, key, transport)).toEqual({
    items: [],
  });
  expect(transport.calls[0].options.method).toBe("GET");
  expect(transport.calls[0].options.headers.Authorization).toBe(
    `Bearer ${key}`,
  );
  await expect(
    providerJson("flashpoint", url, key, mock(200, "invalid")),
  ).rejects.toMatchObject({ code: "UPSTREAM_UNAVAILABLE" });
  await expect(
    providerJson(
      "flashpoint",
      url,
      key,
      mock(200, "<html>login</html>", "text/html"),
    ),
  ).rejects.toMatchObject({ code: "UNSUPPORTED_TYPE" });
  await expect(
    providerJson("flashpoint", url, key, mock(200, "x".repeat(1_000_001))),
  ).rejects.toMatchObject({ code: "SIZE_LIMIT" });
});
