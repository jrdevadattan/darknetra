import https from "node:https";
import { lookup } from "node:dns/promises";
import { createHash } from "node:crypto";
import { providerCredential } from "./providers.mjs";
import { publicUrl, isPublicAddress } from "./public-url.mjs";

const fail = (code, message) => Object.assign(new Error(message), { code });
const ACTOR = "apify~website-content-crawler";
const ACTOR_ID = "aYG0l9s7dbB7j3gbS";
const BUILD = "0.3.96";
const BUILD_ID = "tpKYDXVbrcjHHMqyl";
const ID = /^[a-zA-Z0-9]{17}$/;
export const backupReasons = [
  "retrieval-failed",
  "incomplete-page",
  "explicit-request",
];
const clean = (value, limit) =>
  typeof value === "string" ? value.trim().slice(0, limit) : "";
const redact = (data, token) =>
  JSON.parse(JSON.stringify(data).replaceAll(token, "[REDACTED]"));

// Fixed API host and endpoint family. No arbitrary Actors, code, tasks or webhooks.
export async function apifyJson(path, token, body, transport = {}) {
  const method = body === undefined ? "GET" : "POST";
  const url = new URL(path, "https://api.apify.com");
  const permitted =
    method === "POST"
      ? path === launchPath()
      : path === "/v2/users/me" ||
        path === `/v2/actor-builds/${BUILD_ID}` ||
        /^\/v2\/actor-runs\/[a-zA-Z0-9]{17}\?waitForFinish=30$/.test(path) ||
        /^\/v2\/datasets\/[a-zA-Z0-9]{17}\/items\?format=json&clean=true&limit=2&fields=url,text,markdown,metadata,crawl$/.test(
          path,
        );
  if (!permitted || url.origin !== "https://api.apify.com")
    throw fail(
      "POLICY_DENIED",
      "Only the configured Apify backup endpoints are supported.",
    );
  const resolved = await (transport.lookup || lookup)(url.hostname, {
    all: true,
  });
  if (
    !resolved.length ||
    resolved.some(({ address }) => !isPublicAddress(address))
  )
    throw fail("POLICY_DENIED", "Apify must resolve to a public address.");
  const encoded = body === undefined ? undefined : JSON.stringify(body);
  return new Promise((resolve, reject) => {
    const request = (transport.request || https.request)(
      url,
      {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
          "Accept-Encoding": "identity",
          "User-Agent": "DARKNETRA-Backup-Reader/1.0",
          ...(encoded
            ? {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(encoded),
              }
            : {}),
        },
        lookup: (_host, options, callback) =>
          options.all
            ? callback(null, resolved)
            : callback(null, resolved[0].address, resolved[0].family),
        signal: AbortSignal.timeout(
          path.includes("waitForFinish") ? 40000 : 20000,
        ),
      },
      (response) => {
        response.on("error", () =>
          reject(fail("NETWORK_REQUIRED", "Apify response could not be read.")),
        );
        const status = response.statusCode;
        if (status !== (method === "POST" ? 201 : 200)) {
          response.resume();
          const code =
            status === 401
              ? "AUTH_REQUIRED"
              : status === 403
                ? "ACCESS_DENIED"
                : status === 429
                  ? "RATE_LIMITED"
                  : "UPSTREAM_UNAVAILABLE";
          // Do not echo an upstream body, which can contain credentials or account data.
          reject(
            fail(
              code,
              `Apify returned HTTP ${status}. Check account access or try later; do not bypass restrictions.`,
            ),
          );
          return;
        }
        if (
          !/^application\/(?:[\w.+-]*\+)?json\b/i.test(
            response.headers["content-type"] || "",
          )
        ) {
          response.resume();
          reject(fail("UNSUPPORTED_TYPE", "Apify did not return JSON."));
          return;
        }
        const chunks = [];
        let bytes = 0;
        response.on("data", (chunk) => {
          bytes += chunk.length;
          if (bytes > 1_000_000) {
            reject(fail("SIZE_LIMIT", "Apify response exceeds one megabyte."));
            request.destroy();
          } else chunks.push(chunk);
        });
        response.on("end", () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
          } catch {
            reject(
              fail("UPSTREAM_UNAVAILABLE", "Apify returned unrecognized JSON."),
            );
          }
        });
      },
    );
    request.on("error", () =>
      reject(
        fail(
          "NETWORK_REQUIRED",
          method === "POST"
            ? "Apify launch response was interrupted. A bounded run may already exist; inspect the Apify console before retrying."
            : "Apify connection failed or timed out.",
        ),
      ),
    );
    request.end(encoded);
  });
}

function launchPath() {
  return `/v2/actors/${ACTOR}/runs?build=${BUILD}&timeout=60&memory=1024&maxItems=1&maxTotalChargeUsd=0.05&restartOnError=false&forcePermissionLevel=LIMITED_PERMISSIONS`;
}

export async function apifyTarget(value, resolve = lookup) {
  const url = publicUrl(value);
  if (
    url.hostname.endsWith(".onion") ||
    /(?:^|[.-])(?:local|internal|localhost|invalid)$/.test(url.hostname) ||
    [...url.searchParams.keys()].some((key) =>
      /token|secret|password|api[_-]?key|signature|authorization|session/i.test(
        key,
      ),
    )
  )
    throw fail(
      "POLICY_DENIED",
      "Apify accepts public clearnet URLs without credentials only. Keep onion sources in the local Tor reader.",
    );
  const resolved = await resolve(url.hostname, { all: true });
  if (
    !resolved.length ||
    resolved.some(({ address }) => !isPublicAddress(address))
  )
    throw fail(
      "POLICY_DENIED",
      "The backup source must resolve only to public addresses.",
    );
  return url;
}

export function apifyInput(url) {
  return {
    startUrls: [{ url }],
    crawlerType: "cheerio",
    maxCrawlDepth: 0,
    maxCrawlPages: 1,
    maxResults: 1,
    initialConcurrency: 1,
    maxConcurrency: 1,
    maxRequestRetries: 0,
    maxSessionRotations: 0,
    requestTimeoutSecs: 30,
    // This Actor requires Apify's standard proxy. No residential/geographic
    // selection or session rotation; a denied page must remain a failed read.
    proxyConfiguration: { useApifyProxy: true },
    respectRobotsTxtFile: true,
    useSitemaps: false,
    useLlmsTxt: false,
    keepUrlFragments: false,
    initialCookies: [],
    customHttpHeaders: {},
    signHttpRequests: false,
    ignoreHttpsErrors: false,
    removeCookieWarnings: false,
    clickElementsCssSelector: "",
    maxScrollHeightPixels: 0,
    saveFiles: false,
    saveContentTypes: "",
    saveScreenshots: false,
    saveHtml: false,
    saveHtmlAsFile: false,
    saveMarkdown: true,
    summarize: false,
    debugMode: false,
    debugLog: false,
    storeSkippedUrls: false,
  };
}

export async function apifyStatus(options = {}) {
  const token = await providerCredential("apify", options.env);
  const request = options.request || apifyJson;
  const account = (await request("/v2/users/me", token))?.data;
  if (!account || typeof account.id !== "string")
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Apify account access could not be verified.",
    );
  const build = (await request(`/v2/actor-builds/${BUILD_ID}`, token))?.data;
  if (
    build?.status !== "SUCCEEDED" ||
    build?.actId !== ACTOR_ID ||
    build?.buildNumber !== BUILD
  )
    throw fail(
      "TOOL_UNAVAILABLE",
      "The pinned Apify backup reader is unavailable.",
    );
  return {
    provider: "apify",
    role: "backup",
    authenticated: true,
    actor: ACTOR.replace("~", "/"),
    build: BUILD,
    checkedAt: new Date().toISOString(),
    maxPages: 1,
    maxTotalChargeUsd: 0.05,
    note: "Account and reader build verified. A successful page run is still required to verify extraction. Existing readers remain primary.",
  };
}

function runData(response, previousId) {
  const run = response?.data;
  if (
    !run ||
    !ID.test(run.id) ||
    run.actId !== ACTOR_ID ||
    run.buildId !== BUILD_ID ||
    (previousId && run.id !== previousId) ||
    typeof run.status !== "string"
  )
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Apify returned an unrecognized backup run. Check the console before retrying.",
    );
  return run;
}

export async function apifyPage(value, reason, options = {}) {
  if (!backupReasons.includes(reason))
    throw fail(
      "VALIDATION",
      "Use Apify only after a failed/incomplete public-page read or an explicit request. Supply retrieval-failed, incomplete-page or explicit-request.",
    );
  const url = await apifyTarget(value, options.lookup);
  const token = await providerCredential("apify", options.env);
  if (url.href.includes(token))
    throw fail("POLICY_DENIED", "Do not include credentials in source URLs.");
  const request = options.request || apifyJson;
  // A single launch only. Never retry POST after an ambiguous transport failure.
  let run = runData(await request(launchPath(), token, apifyInput(url.href)));
  for (
    let attempt = 0;
    attempt < 2 &&
    ["READY", "RUNNING", "TIMING-OUT", "ABORTING"].includes(run.status);
    attempt++
  ) {
    try {
      run = runData(
        await request(`/v2/actor-runs/${run.id}?waitForFinish=30`, token),
        run.id,
      );
    } catch {
      throw fail(
        "UPSTREAM_UNAVAILABLE",
        `Apify run ${run.id} could not be checked. Inspect this run in the console before retrying; no second run was started.`,
      );
    }
  }
  if (run.status !== "SUCCEEDED" || !ID.test(run.defaultDatasetId))
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      `Apify run ${run.id} did not provide a completed read (${clean(run.status, 30)}). Inspect the run before retrying. This is not evidence of no matches.`,
    );
  const items = await request(
    `/v2/datasets/${run.defaultDatasetId}/items?format=json&clean=true&limit=2&fields=url,text,markdown,metadata,crawl`,
    token,
  );
  if (
    !Array.isArray(items) ||
    items.length !== 1 ||
    !items[0] ||
    typeof items[0] !== "object"
  )
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Apify did not return exactly one readable page. Empty or unexpected results are a failed check, not no matches.",
    );
  const item = items[0];
  const loaded = await apifyTarget(
    item.crawl?.loadedUrl || item.url,
    options.lookup,
  );
  if (loaded.origin !== url.origin || item.crawl?.httpStatusCode !== 200)
    throw fail(
      "POLICY_DENIED",
      "The backup page changed origin or was not publicly readable. No source has been accepted.",
    );
  const content = clean(item.text, 16000) || clean(item.markdown, 16000);
  if (content.length < 30)
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Apify returned too little readable page content. This is a failed read, not evidence of no matches.",
    );
  const fetchedAt = item.crawl?.loadedTime;
  if (typeof fetchedAt !== "string" || !Number.isFinite(Date.parse(fetchedAt)))
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Apify did not provide a valid retrieval time.",
    );
  const scope =
    "Public-page content retrieved by the Apify backup reader. Source statements remain unverified; compare with independent records.";
  return redact(
    {
      provider: "apify",
      role: "backup",
      backupReason: reason,
      url: loaded.href,
      requestedUrl: url.href,
      title: clean(item.metadata?.title, 200) || loaded.hostname,
      fetchedAt,
      runId: run.id,
      actor: ACTOR.replace("~", "/"),
      build: BUILD,
      maxTotalChargeUsd: 0.05,
      usageUsdPreliminary:
        typeof run.usageTotalUsd === "number" &&
        Number.isFinite(run.usageTotalUsd)
          ? run.usageTotalUsd
          : null,
      contentSha256: createHash("sha256").update(content).digest("hex"),
      truncated: (item.text || item.markdown || "").trim().length > 16000,
      scope,
      text: `${scope}\n\n${content}`,
    },
    token,
  );
}
