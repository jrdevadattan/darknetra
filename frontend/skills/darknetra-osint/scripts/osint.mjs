import http from "node:http";
import https from "node:https";
import { lookup } from "node:dns/promises";
import net from "node:net";
import { pathToFileURL } from "node:url";
import { realpathSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { analyzeFile, offlineTools } from "./files.mjs";
import { readMetadata } from "./metadata.mjs";
import { mlPredict, mlSchema, mlStatus } from "./ml.mjs";
import { apifyPage, apifyStatus } from "./apify.mjs";
import { apifySearch, apifyActor } from "./apify-catalog.mjs";
import { telegramRead, telegramStatus } from "./telegram.mjs";
import { publicUrl, isPublicAddress } from "./public-url.mjs";
export { publicUrl, isPublicAddress } from "./public-url.mjs";
import {
  integrationStatus,
  providerCommands,
  providerLookup,
} from "./providers.mjs";
import { load } from "cheerio";
import { SocksProxyAgent } from "socks-proxy-agent";

const MAX_BYTES = 1_000_000;
const ONIONLAND =
  "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion";
const clean = (text, length = 16000) =>
  text.replace(/\s+/g, " ").trim().slice(0, length);
const fail = (code, message) => Object.assign(new Error(message), { code });
const proxyUrl = () => {
  const url = new URL(
    process.env.DARKNETRA_TOR_SOCKS_URL || "socks5h://127.0.0.1:9050",
  );
  if (
    url.protocol !== "socks5h:" ||
    !["localhost", "127.0.0.1", "[::1]", "research"].includes(url.hostname) ||
    url.username ||
    url.password
  )
    throw fail(
      "CONFIGURATION",
      "Tor must use the local or research-container socks5h proxy without credentials.",
    );
  return url;
};

export async function fetchSource(
  value,
  redirects = 0,
  viaTor = false,
  iconOrigin,
  image = false,
) {
  const url = publicUrl(value);
  if (iconOrigin && url.origin !== iconOrigin)
    throw fail("POLICY_DENIED", "Site icons must remain on the source origin.");
  const onion = url.hostname.endsWith(".onion");
  let agent, resolved;
  if (onion || viaTor)
    agent = new SocksProxyAgent(proxyUrl(), {
      timeout: iconOrigin ? 6000 : 40000,
    });
  if (!onion) {
    resolved = await lookup(url.hostname, { all: true });
    if (
      !resolved.length ||
      resolved.some(({ address }) => !isPublicAddress(address))
    )
      throw fail(
        "POLICY_DENIED",
        "The source resolves to a non-public network address.",
      );
  }
  const response = await new Promise((resolve, reject) => {
    const request = (url.protocol === "https:" ? https : http).get(
      url,
      {
        agent,
        // Pin the validated DNS answer, including on every redirect.
        ...(resolved
          ? {
              lookup: (_host, options, callback) =>
                options.all
                  ? callback(null, resolved)
                  : callback(null, resolved[0].address, resolved[0].family),
            }
          : {}),
        headers: {
          "User-Agent": "DARKNETRA-Public-Research/1.0",
          Accept: image
            ? "image/*,application/octet-stream"
            : iconOrigin
              ? "image/png,image/x-icon,image/webp,image/jpeg,image/gif"
              : "text/html,application/json,application/rss+xml,application/atom+xml,text/plain,application/xml",
        },
        signal: AbortSignal.timeout(
          iconOrigin ? (onion ? 6000 : 4000) : onion ? 40000 : 20000,
        ),
      },
      (res) => {
        const chunks = [];
        let bytes = 0;
        res.on("data", (chunk) => {
          bytes += chunk.length;
          if (
            bytes > (iconOrigin ? 32768 : image ? 8 * 1024 * 1024 : MAX_BYTES)
          )
            request.destroy(
              fail(
                "SIZE_LIMIT",
                `Source exceeds the ${iconOrigin ? "32 KiB icon" : image ? "8 MiB image" : "one-megabyte"} read limit.`,
              ),
            );
          else chunks.push(chunk);
        });
        res.on("error", reject);
        res.on("end", () =>
          resolve({
            status: res.statusCode,
            headers: res.headers,
            body:
              iconOrigin || image
                ? Buffer.concat(chunks)
                : Buffer.concat(chunks).toString("utf8"),
          }),
        );
      },
    );
    request.on("error", reject);
  }).finally(() => agent?.destroy());
  if ([301, 302, 303, 307, 308].includes(response.status)) {
    if (redirects >= 3 || !response.headers.location)
      throw fail("UPSTREAM_UNAVAILABLE", "Source exceeded the redirect limit.");
    return fetchSource(
      new URL(response.headers.location, url).href,
      redirects + 1,
      viaTor || onion,
      iconOrigin,
      image,
    );
  }
  if (response.status !== 200)
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      `Source returned HTTP ${response.status}.`,
    );
  const mime = response.headers["content-type"] || "";
  if (
    image &&
    !/^(?:image\/(?:jpeg|png|gif|webp|tiff|heic|heif|avif)|application\/octet-stream)(?:;|$)/i.test(
      mime,
    )
  )
    throw fail(
      "UNSUPPORTED_TYPE",
      "Source did not return a supported raster image. Metadata remains unverified.",
    );
  if (
    !iconOrigin &&
    !image &&
    !/^(text\/|application\/(json|[^;]*xml))/i.test(mime)
  )
    throw fail(
      "UNSUPPORTED_TYPE",
      "Source did not return text, HTML, XML or JSON.",
    );
  return {
    url: url.href,
    fetchedAt: new Date().toISOString(),
    mime,
    body: response.body,
  };
}

// Robin's MIT anchor filtering and ordered deduplication, with provider-specific selectors.
export function parseIndex(html, provider, limit = 5) {
  const $ = load(html);
  const hits = [];
  const seen = new Set();
  if ($("#challenge-form,.g-recaptcha,.h-captcha").length)
    throw fail("UPSTREAM_UNAVAILABLE", "The index returned a challenge.");
  if (
    provider === "ahmia" &&
    $("#ahmiaResultsPage #noResults").length &&
    !$("ol.searchResults").length
  )
    return [];
  const rows =
    provider === "onionland"
      ? $(".search-results .result-block")
      : $("#ahmiaResultsPage ol.searchResults li.result");
  rows.slice(0, 2000).each((_i, row) => {
    const entry = $(row);
    if (entry.find(".label-ad,.notice-sponsored-ad").length) return;
    const anchor = entry
      .find(
        provider === "onionland"
          ? '.title a[data-category="text-result"]'
          : "h4 a",
      )
      .first();
    const title = clean(anchor.text(), 300);
    let target =
      provider === "onionland"
        ? entry.find(".link").first().text().trim()
        : anchor.attr("href");
    try {
      const redirect = new URL(target, "https://ahmia.fi");
      if (
        redirect.origin === "https://ahmia.fi" &&
        redirect.pathname.replace(/\/$/, "") === "/search/redirect"
      )
        target = redirect.searchParams.get("redirect_url");
      const url = publicUrl(target);
      if (
        !url.hostname.endsWith(".onion") ||
        title.length < 4 ||
        url.pathname.toLowerCase().includes("search")
      )
        return;
      const key = url.href.replace(/\/$/, "");
      if (!seen.has(key)) {
        seen.add(key);
        hits.push({ title, url: url.href, targetFetched: false });
      }
    } catch {
      /* Malformed index entries are omitted. */
    }
  });
  if (!hits.length)
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "The index did not return recognizable search results.",
    );
  return hits.slice(0, limit);
}

export async function robin(query, limit) {
  if (!query?.trim() || query.length > 1000)
    throw fail("VALIDATION", "Enter a query of 1–1000 characters.");
  const warnings = [];
  for (const [provider, url] of [
    ["onionland", `${ONIONLAND}/search?q=${encodeURIComponent(query)}`],
    ["ahmia", `https://ahmia.fi/search/?q=${encodeURIComponent(query)}`],
  ]) {
    try {
      const source = await fetchSource(url);
      return {
        provider,
        source: source.url,
        fetchedAt: source.fetchedAt,
        hits: parseIndex(source.body, provider, limit),
        warnings,
        scope:
          "Public index entries only. Target pages were not fetched; availability, ownership and allegations are unverified.",
      };
    } catch (error) {
      warnings.push({
        provider,
        code: error.code || "NETWORK_REQUIRED",
        message: safeError(error),
      });
    }
  }
  throw Object.assign(
    fail(
      "UPSTREAM_UNAVAILABLE",
      "Robin could not read either index. Check local Tor and the provider status.",
    ),
    { attempts: warnings },
  );
}

export function parsePage(source) {
  const $ = load(source.body);
  $("script,style,noscript,template,svg,form").remove();
  const title = clean($("title").text(), 300);
  const main = $("main,article").first();
  const text = clean(
    source.mime.includes("html")
      ? main.length
        ? main.text()
        : $.root().text()
      : source.body,
    Number.MAX_SAFE_INTEGER,
  );
  const base = publicUrl(source.url);
  const found = new Map();
  if (source.mime.includes("html")) {
    // Only explicit anchors from this response; never invent or fetch destinations.
    // Resolve against the retrieved URL, not an untrusted cross-origin <base> tag.
    for (const element of $("a[href]").toArray()) {
      const href = ($(element).attr("href") || "").trim();
      if (!href || href.startsWith("#")) continue;
      try {
        const url = publicUrl(new URL(href, base).href);
        if (url.href === base.href || found.has(url.href)) continue;
        found.set(url.href, {
          url: url.href,
          title: clean($(element).text(), 180) || url.hostname,
          sameSite: url.hostname === base.hostname,
          targetFetched: false,
        });
      } catch {
        // Non-web, malformed and non-public locators are not actionable links.
      }
    }
  }
  const allLinks = [...found.values()];
  const sameSite = allLinks.filter((link) => link.sameSite);
  const external = allLinks.filter((link) => !link.sameSite);
  const links = [...sameSite, ...external].slice(0, 100);
  const foundImages = new Map();
  if (source.mime.includes("html")) {
    const addImage = (href, title) => {
      if (!href || /^(?:data:|blob:)/i.test(href)) return;
      try {
        const url = publicUrl(new URL(href, base).href);
        if (!foundImages.has(url.href))
          foundImages.set(url.href, {
            url: url.href,
            title: clean(title || "Referenced image", 180),
            sameSite: url.hostname === base.hostname,
            targetFetched: false,
          });
      } catch {
        /* Only usable explicit public image references. */
      }
    };
    for (const element of $(
      "img, picture source, meta[property='og:image'], meta[name='twitter:image']",
    ).toArray()) {
      const el = $(element);
      const title = el.attr("alt") || el.attr("title");
      for (const attr of ["src", "data-src", "content"])
        addImage(el.attr(attr), title);
      const srcset = el.attr("srcset") || "";
      if (!/data:/i.test(srcset))
        for (const candidate of srcset.split(","))
          addImage(candidate.trim().split(/\s+/)[0], title);
    }
  }
  const images = [...foundImages.values()].slice(0, 40);
  return {
    url: source.url,
    fetchedAt: source.fetchedAt,
    title,
    text: text.slice(0, 16000),
    textTruncated: text.length > 16000,
    links,
    images,
    imageSummary: {
      unique: foundImages.size,
      returned: images.length,
      truncated: foundImages.size > images.length,
      scope:
        "Explicit image references in this response only. Image bytes and metadata have not been read; dynamic images may be absent.",
    },
    linkSummary: {
      unique: allLinks.length,
      sameSite: sameSite.length,
      external: external.length,
      returned: links.length,
      truncated: allLinks.length > links.length,
      scope:
        "Links in this retrieved response only. Listed destinations have not been read; this is not a whole-site inventory.",
    },
  };
}

export async function imageMetadata(
  value,
  reader = fetchSource,
  extractor = readMetadata,
) {
  const requested = publicUrl(value);
  const source = await reader(
    requested.href,
    0,
    requested.hostname.endsWith(".onion"),
    undefined,
    true,
  );
  const bytes = source.body;
  if (
    !Buffer.isBuffer(bytes) ||
    !bytes.length ||
    bytes.length > 8 * 1024 * 1024
  )
    throw fail("SIZE_LIMIT", "Provide a nonempty image no larger than 8 MiB.");
  const hex = bytes.subarray(0, 12).toString("hex");
  const raster =
    /^(?:89504e470d0a1a0a|ffd8ff|474946383[79]61|49492a00|4d4d002a)/.test(
      hex,
    ) ||
    (bytes.subarray(0, 4).toString() === "RIFF" &&
      bytes.subarray(8, 12).toString() === "WEBP") ||
    (bytes.subarray(4, 8).toString() === "ftyp" &&
      /^(?:heic|heix|hevc|hevx|mif1|msf1|avif|avis)$/.test(
        bytes.subarray(8, 12).toString(),
      ));
  if (!raster)
    throw fail(
      "UNSUPPORTED_TYPE",
      "The returned bytes are not a supported raster image. Metadata remains unverified.",
    );
  const metadata = await extractor(bytes);
  return {
    ...metadata,
    url: source.url,
    requestedUrl: requested.href,
    title: `Image metadata · ${new URL(source.url).pathname.split("/").pop() || requested.hostname}`,
    fetchedAt: source.fetchedAt,
    mime: source.mime,
    size: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    scope:
      "Read-only metadata from these retrieved image bytes. The hash identifies this response, not an earlier original. Bytes were processed in memory and are not archived.",
  };
}

export function iconData(bytes) {
  if (!Buffer.isBuffer(bytes) || !bytes.length || bytes.length > 32768) return;
  const hex = bytes.subarray(0, 12).toString("hex");
  const mime = hex.startsWith("89504e470d0a1a0a")
    ? "image/png"
    : hex.startsWith("00000100")
      ? "image/x-icon"
      : hex.startsWith("ffd8ff")
        ? "image/jpeg"
        : /^474946383[79]61/.test(hex)
          ? "image/gif"
          : hex.startsWith("52494646") &&
              bytes.subarray(8, 12).toString() === "WEBP"
            ? "image/webp"
            : undefined;
  return mime ? `data:${mime};base64,${bytes.toString("base64")}` : undefined;
}

// Presentation only: fetch at most two small same-origin raster icons through
// the same validated read-only transport. Missing icons never fail the page.
export async function faviconFor(source, reader = fetchSource) {
  const base = publicUrl(source.url);
  const $ = load(source.body);
  const candidates = [];
  for (const element of $("link[rel]").toArray().slice(0, 50)) {
    const rel = ($(element).attr("rel") || "").toLowerCase().split(/\s+/);
    if (!rel.includes("icon") && !rel.includes("apple-touch-icon")) continue;
    try {
      const url = publicUrl(new URL($(element).attr("href"), base).href);
      if (url.origin === base.origin && !/\.svg(?:\?|$)/i.test(url.href))
        candidates.push(url.href);
    } catch {
      /* Unusable icon references use the local fallback. */
    }
  }
  const urls = [
    ...new Set([...candidates.slice(0, 1), new URL("/favicon.ico", base).href]),
  ];
  for (const url of urls) {
    try {
      const icon = await reader(
        url,
        0,
        base.hostname.endsWith(".onion"),
        base.origin,
      );
      const data = iconData(icon.body);
      if (data) return data;
    } catch {
      /* Optional display asset: the source result is still valid. */
    }
  }
}

export function parseFeed(source, limit = 5) {
  const $ = load(source.body, { xmlMode: true });
  if (!$("rss,feed,RDF, rdf\\:RDF").length)
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Source is not a recognized RSS or Atom feed.",
    );
  return {
    url: source.url,
    fetchedAt: source.fetchedAt,
    entries: $("item,entry")
      .slice(0, limit)
      .toArray()
      .map((row) => {
        const item = $(row);
        let url;
        try {
          url = publicUrl(
            new URL(
              item.find("link").attr("href") || item.find("link").text().trim(),
              source.url,
            ).href,
          ).href;
        } catch {
          /* No valid link. */
        }
        return {
          title: clean(item.find("title").first().text(), 300),
          url,
          published: clean(
            item.find("pubDate,published,updated").first().text(),
            100,
          ),
          summary: clean(
            load(
              item.find("description,summary,content").first().text(),
            ).text(),
            1200,
          ),
        };
      }),
  };
}

async function status() {
  const proxy = proxyUrl();
  const torProxyListening = await new Promise((resolve) => {
    const socket = net.connect({
      host: proxy.hostname.replace(/^\[|\]$/g, ""),
      port: Number(proxy.port || 9050),
    });
    const done = (result) => {
      socket.destroy();
      resolve(result);
    };
    socket.setTimeout(1500, () => done(false));
    socket.on("connect", () => done(true));
    socket.on("error", () => done(false));
  });
  return {
    runtime: "Codex CLI skill",
    commands: [
      "integrations",
      "telegram-status",
      "telegram-read",
      "ml-status",
      "ml-schema",
      "ml-predict",
      "apify-status",
      "apify-page",
      "apify-search",
      "apify-actor",
      ...providerCommands,
      "robin",
      "page",
      "feed",
      "wayback",
      "tor-check",
      "catalog",
      "file-info",
      "file-text",
      "metadata",
      "image-metadata",
      "pcap-summary",
      "yara",
    ],
    offline: await offlineTools(),
    integrations: (await integrationStatus()).providers,
    telegram: {
      tokenConfigured: Boolean(process.env.TELEGRAM_BOT_TOKEN),
      chatConfigured: Boolean(process.env.TELEGRAM_CHAT_ID),
      command: "telegram-status",
    },
    ml: await mlStatus(),
    torProxyListening,
    note: torProxyListening
      ? "Local proxy is listening; an actual source read verifies Tor connectivity."
      : "Start Tor on port 9050 or set DARKNETRA_TOR_SOCKS_URL. Public-web commands remain available.",
  };
}

function safeError(error) {
  return [
    "VALIDATION",
    "POLICY_DENIED",
    "CONFIGURATION",
    "UPSTREAM_UNAVAILABLE",
    "SIZE_LIMIT",
    "UNSUPPORTED_TYPE",
    "TOOL_UNAVAILABLE",
    "METADATA_UNREADABLE",
    "MODEL_UNAVAILABLE",
    "MODEL_INCOMPATIBLE",
    "AUTH_REQUIRED",
    "ACCESS_DENIED",
    "RATE_LIMITED",
    "NOT_FOUND",
  ].includes(error.code)
    ? error.message
    : "Source connection failed or timed out.";
}

export async function main([command, value, count]) {
  if (command === "image-metadata") return imageMetadata(value);
  if (command === "telegram-status") return telegramStatus();
  if (command === "telegram-read") return telegramRead(value);
  if (command === "apify-status") return apifyStatus();
  if (command === "apify-search") return apifySearch(value, count);
  if (command === "apify-actor") return apifyActor(value);
  if (command === "apify-page") return apifyPage(value, count);
  if (command === "ml-status") return mlStatus();
  if (command === "ml-schema") return mlSchema();
  if (command === "ml-predict") return mlPredict(value);
  if (command === "integrations") return integrationStatus();
  if (providerCommands.includes(command))
    return providerLookup(command, value, count);
  if (
    ["file-info", "file-text", "metadata", "pcap-summary", "yara"].includes(
      command,
    )
  )
    return analyzeFile(command, value, count);
  if (command === "catalog") {
    const catalog = JSON.parse(
      await readFile(
        new URL("../references/tool-catalog.json", import.meta.url),
        "utf8",
      ),
    );
    const integrations = (await integrationStatus()).providers;
    catalog.tools = catalog.tools.map((item) => {
      const provider = integrations.find((entry) => entry.name === item.name);
      return provider
        ? {
            ...item,
            status: provider.state,
            command: provider.command,
            note: `${provider.capability}. ${provider.message || "API access must be verified by an actual lookup."}`,
          }
        : item;
    });
    return {
      ...catalog,
      tools: value
        ? catalog.tools.filter((item) =>
            `${item.name} ${item.category}`
              .toLowerCase()
              .includes(value.toLowerCase()),
          )
        : catalog.tools,
    };
  }
  if (command === "tor-check") {
    const source = await fetchSource(
      "https://check.torproject.org/api/ip",
      0,
      true,
    );
    const checked = JSON.parse(source.body);
    if (checked.IsTor !== true)
      throw fail(
        "UPSTREAM_UNAVAILABLE",
        "The connection was not identified as Tor.",
      );
    return { connected: true, source: source.url, fetchedAt: source.fetchedAt };
  }
  const limit = count === undefined ? 5 : Number(count);
  if (!Number.isInteger(limit) || limit < 1 || limit > 10)
    throw fail("VALIDATION", "Result limit must be 1–10.");
  if (command === "status") return status();
  if (command === "robin") return robin(value, limit);
  if (command === "page") {
    const source = await fetchSource(value);
    return { ...parsePage(source), favicon: await faviconFor(source) };
  }
  if (command === "feed") return parseFeed(await fetchSource(value), limit);
  if (command === "wayback") {
    const url = publicUrl(value);
    const source = await fetchSource(
      `https://archive.org/wayback/available?url=${encodeURIComponent(url.href)}`,
    );
    const snapshot = JSON.parse(source.body).archived_snapshots?.closest;
    return {
      source: source.url,
      fetchedAt: source.fetchedAt,
      requestedUrl: url.href,
      snapshot: snapshot || null,
    };
  }
  throw fail(
    "VALIDATION",
    "Use status, apify-search <generic-query> [1–10], apify-actor <owner/name>, apify-status, apify-page <public-url> <backup-reason>, ml-status, ml-schema, ml-predict <uploaded-json-file>, integrations, catalog [name], flashpoint <indicator> [1–10], recorded-future <domain-or-public-ip>, chainalysis <wallet-address>, tor-check, robin <query> [1–10], page <url>, image-metadata <image-url>, feed <url> [1–10], wayback <url>, file-info <file>, file-text <file>, metadata <file>, pcap-summary <file>, or yara <file> <rules>.",
  );
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href
) {
  try {
    console.log(
      JSON.stringify({ ok: true, data: await main(process.argv.slice(2)) }),
    );
  } catch (error) {
    console.log(
      JSON.stringify({
        ok: false,
        error: {
          code: error.code || "NETWORK_REQUIRED",
          message: safeError(error),
          ...(error.attempts ? { attempts: error.attempts } : {}),
        },
      }),
    );
    process.exitCode = 1;
  }
}
