import { test, expect, vi } from "vitest";
import { EventEmitter } from "node:events";
import {
  apifyPage,
  apifyStatus,
  apifyJson,
  apifyTarget,
  apifyInput,
} from "./apify.mjs";

const key = "SYNTHETIC-private-apify-token";
const env = {
  APIFY_API_TOKEN: key,
  DARKNETRA_PROVIDER_FILE: new URL("SYNTHETIC-missing.json", import.meta.url)
    .pathname,
};
const lookup = async () => [{ address: "93.184.216.34", family: 4 }];
const run = {
  id: "SYNTHETICRUN00001",
  actId: "aYG0l9s7dbB7j3gbS",
  buildId: "tpKYDXVbrcjHHMqyl",
  status: "SUCCEEDED",
  defaultDatasetId: "SYNTHETICDATA0001",
  usageTotalUsd: 0.001,
};
const page = {
  url: "https://example.com/",
  text: "SYNTHETIC public page source material for testing. No case findings.",
  metadata: { title: "SYNTHETIC page", secret: key },
  crawl: {
    httpStatusCode: 200,
    loadedUrl: "https://example.com/",
    loadedTime: "2026-09-08T10:00:00Z",
  },
};

test("backup requires an explicit reason and excludes private/onion/credential targets before any paid call", async () => {
  const request = vi.fn();
  await expect(
    apifyPage("https://example.com/", undefined, { env, lookup, request }),
  ).rejects.toMatchObject({ code: "VALIDATION" });
  for (const url of [
    "http://127.0.0.1/",
    `http://${"a".repeat(56)}.onion/`,
    "https://example.com/?api_key=SYNTHETIC",
    "https://user:pass@example.com/",
  ]) {
    await expect(
      apifyPage(url, "retrieval-failed", { env, lookup, request }),
    ).rejects.toThrow();
  }
  await expect(
    apifyTarget("https://example.com/", async () => [
      { address: "10.0.0.1", family: 4 },
    ]),
  ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  expect(request).not.toHaveBeenCalled();
});

test("one fixed bounded Actor launch yields a timestamped attributed source without secrets", async () => {
  const calls = [];
  const result = await apifyPage("https://example.com/", "explicit-request", {
    env,
    lookup,
    request: async (path, token, input) => {
      calls.push({ path, token, input });
      return input
        ? { data: { ...run, status: "RUNNING" } }
        : path.includes("actor-runs")
          ? { data: run }
          : [page];
    },
  });
  expect(calls.filter((c) => c.input)).toHaveLength(1);
  expect(calls[0].path).toContain("maxTotalChargeUsd=0.05");
  expect(calls[0].path).toContain("timeout=60");
  expect(calls[0].input).toMatchObject({
    crawlerType: "cheerio",
    maxResults: 1,
    maxCrawlDepth: 0,
    maxCrawlPages: 1,
    respectRobotsTxtFile: true,
    maxRequestRetries: 0,
    maxSessionRotations: 0,
    proxyConfiguration: { useApifyProxy: true },
    summarize: false,
  });
  expect(result).toMatchObject({
    role: "backup",
    backupReason: "explicit-request",
    url: page.url,
    runId: run.id,
    fetchedAt: page.crawl.loadedTime,
  });
  expect(result.contentSha256).toMatch(/^[a-f0-9]{64}$/);
  expect(JSON.stringify(result)).not.toContain(key);
  expect(calls.every((c) => c.token === key && !c.path.includes(key))).toBe(
    true,
  );
});

test("failed, empty, cross-origin and malformed responses never become successful reads or new launches", async () => {
  for (const dataset of [
    [],
    [page, page],
    [{ ...page, text: "" }],
    [
      {
        ...page,
        crawl: { ...page.crawl, loadedUrl: "https://elsewhere.example.com/" },
      },
    ],
    [{ ...page, crawl: { ...page.crawl, httpStatusCode: 403 } }],
    [{ ...page, crawl: { httpStatusCode: 200 } }],
  ]) {
    let launches = 0;
    await expect(
      apifyPage(page.url, "incomplete-page", {
        env,
        lookup,
        request: async (_path, _token, input) =>
          input ? (launches++, { data: run }) : dataset,
      }),
    ).rejects.toThrow();
    expect(launches).toBe(1);
  }
  const request = vi.fn().mockRejectedValue(new Error("SYNTHETIC timeout"));
  await expect(
    apifyPage(page.url, "retrieval-failed", { env, lookup, request }),
  ).rejects.toThrow();
  expect(request).toHaveBeenCalledTimes(1);
  const polling = vi
    .fn()
    .mockResolvedValue({ data: { ...run, status: "RUNNING" } });
  await expect(
    apifyPage(page.url, "retrieval-failed", { env, lookup, request: polling }),
  ).rejects.toMatchObject({ code: "UPSTREAM_UNAVAILABLE" });
  expect(polling).toHaveBeenCalledTimes(3);
});

test("account verification makes no paid run and never returns account identity", async () => {
  const request = vi.fn(async (path) => ({
    data: path.includes("users")
      ? { id: "SYNTHETIC-person", email: "SYNTHETIC@example.invalid" }
      : { status: "SUCCEEDED", actId: run.actId, buildNumber: "0.3.96" },
  }));
  const result = await apifyStatus({ env, request });
  expect(result.authenticated).toBe(true);
  expect(request).toHaveBeenCalledTimes(2);
  expect(JSON.stringify(result)).not.toContain("SYNTHETIC");
});

test("API transport restricts destinations, never follows redirects or prints provider bodies", async () => {
  const request = vi.fn((_url, options, done) => {
    expect(options.headers.Authorization).toBe(`Bearer ${key}`);
    const req = new EventEmitter();
    req.end = () => {
      const res = new EventEmitter();
      res.statusCode = 302;
      res.headers = { location: "https://example.com/" };
      res.resume = () => {};
      done(res);
    };
    return req;
  });
  await expect(
    apifyJson("/v2/users/me", key, undefined, { lookup, request }),
  ).rejects.toMatchObject({ code: "UPSTREAM_UNAVAILABLE" });
  expect(request).toHaveBeenCalledTimes(1);
  for (const path of [
    "https://example.com/",
    "/v2/actors/other~actor/runs",
    "/v2/users/me?token=SYNTHETIC",
  ]) {
    await expect(
      apifyJson(path, key, undefined, { lookup, request }),
    ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  }
  expect(request).toHaveBeenCalledTimes(1);
});
