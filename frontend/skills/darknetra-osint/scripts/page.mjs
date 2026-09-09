import { createHash } from "node:crypto";
import { load } from "cheerio";
import { publicUrl } from "./public-url.mjs";

const clean = (value, max = 300) =>
  String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
const fail = (message) =>
  Object.assign(new Error(message), { code: "VALIDATION" });

function reviewFindings(text, url) {
  const patterns = [
    [
      "wallet",
      /\b(?:bc1[ac-hj-np-z02-9]{20,80}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|0x[a-fA-F0-9]{40})\b/g,
    ],
    ["access-required", /\b(?:sign in|log in|login|create an account)\b/gi],
    [
      "payment-reference",
      /\b(?:payment address|send bitcoin|pay with crypto|escrow payment)\b/gi,
    ],
  ];
  const all = [];
  for (const [kind, expression] of patterns) {
    for (const match of text.matchAll(expression)) {
      const offset = match.index;
      const line = text.slice(0, offset).split("\n").length;
      const start = Math.max(text.lastIndexOf("\n", offset) + 1, offset - 130);
      const nextLine = text.indexOf("\n", offset);
      const end = Math.min(
        nextLine < 0 ? text.length : nextLine,
        offset + match[0].length + 180,
      );
      all.push({
        kind,
        value: match[0],
        sourceUrl: url,
        excerpt: text.slice(start, end),
        location: { line, offset, basis: "extracted text" },
        reviewStatus: "needs_review",
      });
      if (all.length >= 36) break;
    }
    if (all.length >= 36) break;
  }
  return all.sort((a, b) => a.location.offset - b.location.offset);
}

export function parsePage(
  source,
  { offset = 0, textLimit = 16000, linkOffset = 0, linkLimit = 100 } = {},
) {
  if (
    !Number.isInteger(offset) ||
    offset < 0 ||
    offset > 1_000_000 ||
    !Number.isInteger(linkOffset) ||
    linkOffset < 0 ||
    linkOffset > 10000
  )
    throw fail(
      "Use a nonnegative text offset up to 1000000 or link offset up to 10000.",
    );
  const html = source.mime.toLowerCase().includes("html");
  const $ = load(source.body);
  const base = publicUrl(source.url);
  let documentBase = base;
  try {
    const declared = publicUrl(
      new URL($("base[href]").first().attr("href") || base.href, base).href,
    );
    if (declared.origin === base.origin) documentBase = declared;
  } catch {
    /* Ignore unusable or cross-origin base declarations. */
  }
  const title = clean($("title").text());
  const scriptCount = $("script").length;
  const passwordFieldPresent = $("input[type='password']").length > 0;
  const challengeMentioned =
    /checking your browser|verify you are human|captcha|access denied/i.test(
      $("title").text() + " " + $("body").text().slice(0, 1000),
    );
  $("script,style,template,svg").remove();
  const found = new Map();
  if (html) {
    for (const element of $("a[href]").toArray()) {
      if ($(element).closest("form").length) continue;
      const href = ($(element).attr("href") || "").trim();
      if (!href || href.startsWith("#")) continue;
      try {
        const url = publicUrl(new URL(href, documentBase).href);
        if (url.href === base.href || found.has(url.href)) continue;
        found.set(url.href, {
          url: url.href,
          title: clean($(element).text(), 180) || url.hostname,
          sameSite: url.hostname === base.hostname,
          targetFetched: false,
        });
      } catch {
        /* Unusable or non-public reference. */
      }
    }
  }
  const allLinks = [...found.values()];
  const sameSite = allLinks.filter((l) => l.sameSite),
    external = allLinks.filter((l) => !l.sameSite);
  const links = [...sameSite, ...external].slice(
    linkOffset,
    linkOffset + linkLimit,
  );
  const foundImages = new Map();
  const addImage = (href, label) => {
    if (!href || /^(?:data:|blob:)/i.test(href)) return;
    try {
      const url = publicUrl(new URL(href, documentBase).href);
      if (!foundImages.has(url.href))
        foundImages.set(url.href, {
          url: url.href,
          title: clean(label || "Referenced image", 180),
          sameSite: url.hostname === base.hostname,
          targetFetched: false,
        });
    } catch {
      /* Only explicit usable image references. */
    }
  };
  if (html)
    for (const element of $(
      "img, picture source, meta[property='og:image'], meta[name='twitter:image']",
    ).toArray()) {
      const el = $(element),
        label = el.attr("alt") || el.attr("title");
      for (const attr of ["src", "data-src", "content"])
        addImage(el.attr(attr), label);
      const srcset = el.attr("srcset") || "";
      if (!/data:/i.test(srcset))
        for (const entry of srcset.split(","))
          addImage(entry.trim().split(/\s+/)[0], label);
    }
  // Keep sibling articles, surrounding context and public form labels. No form is submitted.
  if (html) {
    $("br").replaceWith("\n");
    $(
      "p,div,main,article,section,aside,header,footer,nav,li,tr,h1,h2,h3,h4,h5,h6,pre,blockquote,form",
    )
      .before("\n")
      .after("\n");
    $("td,th").after("\t");
  }
  const rawText = html ? $("body").text() : source.body;
  const text = rawText
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n");
  const javascriptLikely =
    html &&
    scriptCount > 0 &&
    (text.length < 200 ||
      /enable javascript|javascript is required/i.test(text.slice(0, 1500)));
  const warnings = [];
  if (javascriptLikely)
    warnings.push(
      "This may be a JavaScript application shell. Dynamic content has not been rendered.",
    );
  if (passwordFieldPresent)
    warnings.push(
      "Password controls occur in the public HTML. Authenticated content has not been accessed.",
    );
  if (challengeMentioned)
    warnings.push(
      "The response mentions an access check. Do not treat it as the requested underlying content.",
    );
  if (!text) warnings.push("No readable text was extracted.");
  const end = Math.min(text.length, offset + textLimit);
  return {
    url: source.url,
    fetchedAt: source.fetchedAt,
    title,
    sha256: createHash("sha256").update(source.body).digest("hex"),
    hashScope: "Decoded response body; no archived original is implied.",
    text: text.slice(offset, end),
    textOffset: offset,
    textLength: text.length,
    textTruncated: end < text.length,
    nextOffset: end < text.length ? end : null,
    startLine: text.slice(0, offset).split("\n").length,
    links,
    nextLinkOffset:
      linkOffset + links.length < allLinks.length
        ? linkOffset + links.length
        : null,
    images: [...foundImages.values()].slice(0, 40),
    findings: reviewFindings(text, source.url),
    findingsScope:
      "Lexical references for contextual review only. An address, payment term or login mention does not establish wrongdoing, ownership or access availability.",
    access: {
      passwordFieldPresent,
      challengeMentioned,
      formsSubmitted: false,
      authenticated: false,
    },
    extraction: {
      completeSite: false,
      renderedJavascript: false,
      javascriptLikely,
      warnings,
      scope:
        "All readable text in this response body, including surrounding navigation. Hidden, authenticated and dynamic content may be absent.",
    },
    imageSummary: {
      unique: foundImages.size,
      returned: Math.min(40, foundImages.size),
      truncated: foundImages.size > 40,
      scope:
        "Explicit image references only; image bytes and metadata have not been read.",
    },
    linkSummary: {
      unique: allLinks.length,
      sameSite: sameSite.length,
      external: external.length,
      returned: links.length,
      offset: linkOffset,
      truncated: linkOffset + links.length < allLinks.length,
      scope:
        "Explicit links in this response only. Listed destinations have not been read; this is not a whole-site inventory.",
    },
  };
}
