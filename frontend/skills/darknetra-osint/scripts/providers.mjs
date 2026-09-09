import https from "node:https";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { lookup } from "node:dns/promises";
import net from "node:net";
import ipaddr from "ipaddr.js";

const fail = (code, message) => Object.assign(new Error(message), { code });
const definitions = [
  {
    id: "flashpoint",
    name: "Flashpoint",
    host: "api.flashpoint.io",
    header: "Authorization",
    env: "FLASHPOINT_API_TOKEN",
    command: "flashpoint <indicator> [1–10]",
    capability: "Indicator search and risk context",
    setupUrl: "https://app.flashpoint.io/",
  },
  {
    id: "recorded-future",
    name: "Recorded Future",
    host: "api.recordedfuture.com",
    header: "X-RFToken",
    env: "RECORDED_FUTURE_API_TOKEN",
    command: "recorded-future <domain-or-public-ip>",
    capability: "Domain and IP intelligence lookup",
    setupUrl: "https://docs.recordedfuture.com/reference/get-started",
  },
  {
    id: "chainalysis",
    name: "Chainalysis Sanctions",
    host: "public.chainalysis.com",
    header: "X-API-Key",
    env: "CHAINALYSIS_API_KEY",
    command: "chainalysis <wallet-address>",
    capability: "Direct sanctions screening; excludes Reactor and KYT",
    setupUrl: "https://public.chainalysis.com/",
  },
  {
    id: "apify",
    name: "Apify",
    env: "APIFY_API_TOKEN",
    command: "apify-page <public-url> <backup-reason>",
    capability:
      "Backup public-page reader; Robin and existing readers stay primary",
    setupUrl: "https://console.apify.com/settings/integrations",
  },
];
const text = (value, limit = 1200) =>
  typeof value === "string"
    ? value.replace(/\s+/g, " ").trim().slice(0, limit)
    : "";
const object = (value) =>
  value && typeof value === "object" && !Array.isArray(value);
export const providerCommands = definitions
  .filter((p) => p.host)
  .map((p) => p.id);

export async function providerCredential(id, env = process.env) {
  const provider = definitions.find((p) => p.id === id);
  if (!provider) throw fail("VALIDATION", "Unknown intelligence provider.");
  const token = (await credentials(env))[id];
  if (!token)
    throw fail(
      "AUTH_REQUIRED",
      `${provider.name} credentials are required. Configure providers.json locally; do not paste keys into chat.`,
    );
  return token;
}

// The file is inherited by CLI skills without putting tokens in prompts or argv.
// It lives outside case folders and is never included in the browser response.
async function credentials(env = process.env) {
  let saved = {};
  const file =
    env.DARKNETRA_PROVIDER_FILE ||
    fileURLToPath(
      new URL("../../../.codex-chat/providers.json", import.meta.url),
    );
  try {
    const body = await readFile(file, "utf8");
    if (body.length > 16384)
      throw fail("CONFIGURATION", "Provider credentials file is too large.");
    saved = JSON.parse(body);
    if (!object(saved)) throw new Error();
  } catch (error) {
    if (error.code !== "ENOENT")
      throw fail(
        "CONFIGURATION",
        "Could not read providers.json. Check its JSON format and local file permissions.",
      );
  }
  const result = {};
  for (const provider of definitions) {
    const value = env[provider.env] || saved[provider.id] || "";
    if (
      typeof value !== "string" ||
      /[\x00-\x20\x7f]/.test(value) ||
      value.length > 4096
    )
      throw fail(
        "CONFIGURATION",
        "Provider tokens must be single-line strings without spaces.",
      );
    result[provider.id] = value;
  }
  return result;
}
export async function integrationStatus(env = process.env) {
  let values = {},
    configurationError;
  try {
    values = await credentials(env);
  } catch (error) {
    configurationError = error.message;
  }
  return {
    providers: definitions.map(
      ({ id, name, command, capability, setupUrl }) => ({
        id,
        name,
        command,
        capability,
        setupUrl,
        state: configurationError
          ? "configuration_error"
          : values[id]
            ? "configured_unverified"
            : "credentials_required",
        ...(configurationError ? { message: configurationError } : {}),
      }),
    ),
    note: "Configured credentials are not proof of service access. Only a successful lookup verifies the requested API and account entitlement.",
  };
}

function providerUrl(provider, value) {
  const url = new URL(value);
  const allowedPath =
    provider.id === "flashpoint"
      ? url.pathname === "/technical-intelligence/v2/indicators"
      : provider.id === "recorded-future"
        ? /^\/v2\/(domain|ip)\/[^/]+$/.test(url.pathname)
        : /^\/api\/v1\/address\/[a-zA-Z0-9]+$/.test(url.pathname);
  if (
    url.protocol !== "https:" ||
    url.hostname !== provider.host ||
    url.username ||
    url.password ||
    url.port ||
    !allowedPath
  )
    throw fail(
      "POLICY_DENIED",
      "Provider credentials can only be sent to the supported provider endpoint.",
    );
  return url;
}
export async function providerJson(providerId, value, token, transport = {}) {
  const provider = definitions.find((p) => p.id === providerId);
  if (!provider?.host)
    throw fail("VALIDATION", "Unknown intelligence provider.");
  const url = providerUrl(provider, value);
  const resolved = await (transport.lookup || lookup)(url.hostname, {
    all: true,
  });
  if (
    !resolved.length ||
    resolved.some(({ address }) => {
      try {
        return ipaddr.process(address).range() !== "unicast";
      } catch {
        return true;
      }
    })
  )
    throw fail("POLICY_DENIED", "Provider must resolve to a public address.");
  return new Promise((resolve, reject) => {
    const request = (transport.get || https.get)(
      url,
      {
        method: "GET",
        headers: {
          Accept: "application/json",
          "Accept-Encoding": "identity",
          "User-Agent": "DARKNETRA-Research/1.0",
          [provider.header]:
            provider.id === "flashpoint" ? `Bearer ${token}` : token,
        },
        lookup: (_host, options, callback) =>
          options.all
            ? callback(null, resolved)
            : callback(null, resolved[0].address, resolved[0].family),
        signal: AbortSignal.timeout(20000),
      },
      (response) => {
        response.on("error", () =>
          reject(
            fail("NETWORK_REQUIRED", "Provider response could not be read."),
          ),
        );
        // Never follow redirects with an API credential, even to the same host.
        const code = response.statusCode;
        if (code !== 200) {
          response.resume();
          const error =
            code === 401
              ? ["AUTH_REQUIRED", "Provider rejected the API credential."]
              : code === 403
                ? [
                    "ACCESS_DENIED",
                    "Provider access is denied. Check the account licence and API permissions.",
                  ]
                : code === 429
                  ? [
                      "RATE_LIMITED",
                      "Provider rate limit reached. Wait before another lookup.",
                    ]
                  : code === 404
                    ? [
                        "NOT_FOUND",
                        "The provider did not return a record for this request.",
                      ]
                    : [
                        "UPSTREAM_UNAVAILABLE",
                        `Provider returned HTTP ${code}.`,
                      ];
          reject(fail(...error));
          return;
        }
        if (
          !/^application\/(?:[\w.+-]*\+)?json\b/i.test(
            response.headers["content-type"] || "",
          )
        ) {
          response.resume();
          reject(fail("UNSUPPORTED_TYPE", "Provider did not return JSON."));
          return;
        }
        const chunks = [];
        let bytes = 0;
        response.on("data", (chunk) => {
          bytes += chunk.length;
          if (bytes > 1_000_000)
            request.destroy(
              fail(
                "SIZE_LIMIT",
                "Provider response exceeds the one-megabyte limit.",
              ),
            );
          else chunks.push(chunk);
        });
        response.on("error", () =>
          reject(
            fail("NETWORK_REQUIRED", "Provider response could not be read."),
          ),
        );
        response.on("end", () => {
          try {
            const data = JSON.parse(Buffer.concat(chunks).toString("utf8"));
            if (!object(data)) throw new Error();
            resolve(data);
          } catch {
            reject(
              fail(
                "UPSTREAM_UNAVAILABLE",
                "Provider returned an unrecognized response.",
              ),
            );
          }
        });
      },
    );
    request.on("error", (error) =>
      reject(
        fail(
          error.code === "SIZE_LIMIT" ? "SIZE_LIMIT" : "NETWORK_REQUIRED",
          error.code === "SIZE_LIMIT"
            ? "Provider response exceeds the one-megabyte limit."
            : "Provider connection failed or timed out.",
        ),
      ),
    );
  });
}

function selector(value) {
  if (
    typeof value !== "string" ||
    !value.trim() ||
    value.length > 512 ||
    /[\s\x00-\x1f\x7f]/.test(value)
  )
    throw fail("VALIDATION", "Supply one domain, public IP, URL or file hash.");
  return value;
}
function domainOrIp(value) {
  value = selector(value).toLowerCase();
  if (net.isIP(value)) {
    if (ipaddr.process(value).range() !== "unicast")
      throw fail("VALIDATION", "Use a public IP address.");
    return { type: "ip", value, id: `ip:${value}` };
  }
  if (
    value.length > 253 ||
    !/^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$/.test(
      value,
    ) ||
    value.endsWith(".localhost")
  )
    throw fail(
      "VALIDATION",
      "Supply a domain name or public IP, without a scheme or path.",
    );
  return { type: "domain", value, id: `idn:${value}` };
}
function link(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "https:" && !url.username && !url.password)
      return url.href;
  } catch {
    /* absent provider link */
  }
}
export function normalizeProvider(
  provider,
  data,
  query,
  requestUrl,
  limit = 5,
) {
  const base = {
    provider,
    url: requestUrl,
    fetchedAt: new Date().toISOString(),
    title: `${definitions.find((p) => p.id === provider)?.name} · ${query}`,
    scope:
      "Provider-reported intelligence, not a confirmed identity, ownership link or finding.",
  };
  if (provider === "flashpoint") {
    if (
      !Array.isArray(data.items) ||
      data.items.some(
        (item) =>
          !object(item) ||
          typeof item.value !== "string" ||
          typeof item.id !== "string",
      )
    )
      throw fail(
        "UPSTREAM_UNAVAILABLE",
        "Flashpoint returned an unrecognized indicator response.",
      );
    const records = data.items.slice(0, limit).map((item) => ({
      id: text(item.id, 200),
      value: text(item.value, 512),
      type: text(item.type, 60),
      assessment: text(item.score?.value, 80),
      lastSeenAt: text(item.last_seen_at, 80),
      url: link(item.platform_urls?.ignite),
    }));
    return {
      ...base,
      records,
      truncated: data.items.length > limit || Boolean(data.pagination?.next),
      text: records.length
        ? records
            .map(
              (r) =>
                `Indicator: ${r.value}\nType: ${r.type || "not supplied"}\nProvider assessment: ${r.assessment || "not supplied"}${r.lastSeenAt ? `\nLast seen: ${r.lastSeenAt}` : ""}${r.url ? `\nProvider record: ${r.url}` : ""}`,
            )
            .join("\n\n")
        : "No matching indicator records were returned by this Flashpoint query. This does not establish that a threat or source does not exist.",
    };
  }
  if (provider === "recorded-future") {
    const d = data.data;
    if (!object(d) || !object(d.entity) || typeof d.entity.id !== "string")
      throw fail(
        "UPSTREAM_UNAVAILABLE",
        "Recorded Future returned an unrecognized entity response.",
      );
    const rules = Array.isArray(d.risk?.evidenceDetails)
      ? d.risk.evidenceDetails.slice(0, 10).map((r) => ({
          rule: text(r.rule, 200),
          assessment: text(r.evidenceString),
          at: text(r.timestamp, 80),
        }))
      : [];
    const riskScore =
      typeof d.risk?.score === "number" && Number.isFinite(d.risk.score)
        ? d.risk.score
        : null;
    return {
      ...base,
      entity: { id: text(d.entity.id, 300), name: text(d.entity.name, 300) },
      riskScore,
      rules,
      intelCard: link(d.intelCard),
      text: `Entity: ${text(d.entity.name, 300) || query}\nProvider risk score: ${riskScore ?? "not supplied"}\n${text(d.risk?.riskSummary)}\n${rules.map((r) => `${r.rule}: ${r.assessment}`).join("\n")}${link(d.intelCard) ? `\nProvider record: ${link(d.intelCard)}` : ""}\nA provider risk score is an assessment, not proof of wrongdoing.`,
    };
  }
  if (
    !Array.isArray(data.identifications) ||
    data.identifications.some(
      (item) => !object(item) || typeof item.category !== "string",
    )
  )
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Chainalysis returned an unrecognized sanctions response.",
    );
  const identifications = data.identifications.slice(0, 20).map((item) => ({
    category: text(item.category, 100),
    name: text(item.name, 250),
    description: text(item.description),
    url: link(item.url),
  }));
  return {
    ...base,
    identifications,
    truncated: data.identifications.length > 20,
    scope:
      "Direct sanctions-screening response only. No Reactor tracing, KYT monitoring, indirect exposure analysis or ownership determination.",
    text: identifications.length
      ? identifications
          .map(
            (r) =>
              `Provider identification: ${r.name || "unnamed"}\nCategory: ${r.category}\n${r.description}${r.url ? `\nReference: ${r.url}` : ""}`,
          )
          .join("\n\n")
      : "No identifications were returned by the Chainalysis sanctions API for this address. This is not a clean-wallet determination and says nothing about indirect exposure or ownership.",
  };
}
export async function providerLookup(provider, value, count, options = {}) {
  if (!providerCommands.includes(provider))
    throw fail("VALIDATION", "Unknown intelligence provider.");
  const limit = count === undefined ? 5 : Number(count);
  if (!Number.isInteger(limit) || limit < 1 || limit > 10)
    throw fail("VALIDATION", "Result limit must be 1–10.");
  let url;
  if (provider === "flashpoint") {
    value = selector(value);
    if (!/^[a-f\d]{32,128}$/i.test(value)) {
      if (/^https?:\/\//.test(value)) {
        const parsed = new URL(value);
        if (parsed.username || parsed.password || parsed.port)
          throw fail(
            "VALIDATION",
            "Do not include URL credentials or custom ports.",
          );
        domainOrIp(parsed.hostname);
      } else domainOrIp(value);
    }
    url = new URL(
      "https://api.flashpoint.io/technical-intelligence/v2/indicators",
    );
    url.searchParams.set("ioc_value", value);
    url.searchParams.set("size", String(limit));
  } else if (provider === "recorded-future") {
    const entity = domainOrIp(value);
    url = new URL(
      `https://api.recordedfuture.com/v2/${entity.type}/${encodeURIComponent(entity.id)}`,
    );
    url.searchParams.set("fields", "entity,risk,intelCard");
  } else {
    if (typeof value !== "string" || !/^[a-zA-Z0-9]{20,128}$/.test(value))
      throw fail(
        "VALIDATION",
        "Supply one wallet address using only letters and digits (20–128 characters).",
      );
    url = new URL(`https://public.chainalysis.com/api/v1/address/${value}`);
  }
  const values = await credentials(options.env);
  if (!values[provider])
    throw fail(
      "AUTH_REQUIRED",
      `${definitions.find((p) => p.id === provider).name} credentials are required. Configure providers.json locally; do not paste keys into chat.`,
    );
  const data = await (options.request || providerJson)(
    provider,
    url.href,
    values[provider],
  );
  const result = normalizeProvider(provider, data, value, url.href, limit);
  result.text = `${result.scope}\n\n${result.text}`;
  return JSON.parse(
    JSON.stringify(result).replaceAll(values[provider], "[REDACTED]"),
  );
}
