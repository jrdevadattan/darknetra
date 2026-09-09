import type { Activity, RunSource } from "./chat-types";

export function sourceUrl(value: unknown) {
  if (typeof value !== "string" || value.length > 4000) return;
  try {
    const url = new URL(value);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password
    )
      return;
    url.hash = "";
    return url.href;
  } catch {
    return;
  }
}
const short = (value: unknown, max = 1500) =>
  typeof value === "string" ? value.slice(0, max) : "";

export function faviconData(value: unknown) {
  return typeof value === "string" &&
    value.length <= 44000 &&
    /^data:image\/(?:png|x-icon|jpeg|gif|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(
      value,
    )
    ? value
    : undefined;
}
export function commandTarget(command = "") {
  return sourceUrl(
    command.match(
      /osint\.mjs["']?\s+(?:page|page-section|site-review|feed|wayback|apify-page|image-metadata)\s+["']?(https?:\/\/[^\s"'<>]+)/,
    )?.[1],
  );
}

export function commandLabel(command = "") {
  const helper = command.match(/osint\.mjs["']?\s+([\w-]+)/)?.[1];
  const labels: Record<string, string> = {
    page: "Reading a source",
    "page-section": "Reading a source section",
    "site-review": "Reviewing linked pages",
    "wallet-review": "Reviewing public transactions",
    robin: "Checking public indexes",
    wayback: "Checking archive history",
    feed: "Reading published updates",
    "file-info": "Identifying a file",
    "file-text": "Reading an attached file",
    metadata: "Examining file metadata",
    "image-metadata": "Examining image metadata",
    "pcap-summary": "Reviewing a capture file",
    yara: "Checking file signatures",
    status: "Checking research tools",
    "tor-check": "Checking connectivity",
    integrations: "Checking intelligence access",
    flashpoint: "Checking threat intelligence",
    "recorded-future": "Reviewing domain intelligence",
    chainalysis: "Reviewing sanctions records",
    "ml-status": "Checking the transaction model",
    "ml-schema": "Checking required transaction inputs",
    "ml-predict": "Analysing a transaction graph",
    "apify-status": "Checking the backup reader",
    "telegram-status": "Checking Telegram bot access",
    "telegram-read": "Reading configured Telegram messages",
    "apify-page": "Reading a source with the backup reader",
    "apify-search": "Finding backup scrapers",
    "apify-actor": "Reviewing a backup scraper",
    catalog: "Checking available tools",
  };
  return (
    labels[helper || ""] ||
    (command.includes("SKILL.md")
      ? "Preparing the review"
      : "Reviewing information")
  );
}

// Only the maintained helper's bounded JSON contract becomes source data.
// Arbitrary shell output, configuration and reasoning never enter this record.
export function helperResult(
  command: string,
  output?: string,
): Pick<Activity, "result" | "sources" | "coverage"> {
  if (!command.includes("osint.mjs") || !output || output.length > 1024 * 1024)
    return {};
  let parsed;
  try {
    parsed = JSON.parse(output);
  } catch {
    return {};
  }
  if (!parsed || typeof parsed !== "object") return {};
  if (
    parsed.ok === false &&
    /osint\.mjs["']?\s+(?:metadata|image-metadata)\b/.test(command)
  )
    return {
      result: `Metadata remains unverified. ${short(parsed.error?.message, 500) || "The image could not be checked."}`,
    };
  if (parsed.ok === false)
    return {
      result: `This check could not be completed${typeof parsed.error?.code === "string" ? ` (${short(parsed.error.code, 80)})` : ""}. This does not establish that there are no matches.`,
    };
  const d = parsed.data;
  if (parsed.ok !== true || !d || typeof d !== "object") return {};
  if (d.analysis === "site-review") return siteReviewResult(d);
  if (d.analysis === "wallet_review") return walletReviewResult(d);
  if (d.catalog === true && d.provider === "apify")
    return { result: short(d.text, 1500), sources: [] };
  const sources: RunSource[] = [];
  const at =
    typeof d.fetchedAt === "string" && Number.isFinite(Date.parse(d.fetchedAt))
      ? d.fetchedAt
      : undefined;
  function add(
    value: unknown,
    title: unknown,
    kind: RunSource["kind"],
    status: RunSource["status"],
    excerpt?: unknown,
    parentId?: string,
  ) {
    const url = sourceUrl(value);
    if (!url) return;
    const id = `url:${url}`;
    sources.push({
      id,
      url,
      title: short(title, 200) || new URL(url).hostname,
      kind,
      status,
      at,
      excerpt: short(excerpt),
      parentId,
    });
    return id;
  }
  if (typeof d.text === "string" && sourceUrl(d.url)) {
    add(
      d.url,
      d.title,
      "page",
      d.analysis === "metadata" ? "analysed" : "retrieved",
      d.text,
    );
    if (/^[a-f\d]{64}$/i.test(d.sha256 || "")) sources[0].sha256 = d.sha256;
    if (d.analysis === "metadata") {
      sources[0].excerpt = short(d.text, 16000);
    } else {
      Object.assign(sources[0], pageDetails(d, sourceUrl(d.url)!));
      if (Number.isSafeInteger(d.textOffset) && d.textOffset > 0) {
        sources[0].parentId = sources[0].id;
        sources[0].parentRelation = "has text section";
        sources[0].id = `${sources[0].id}:text-offset:${d.textOffset}`;
        sources[0].title = `${sources[0].title} · text offset ${d.textOffset}`;
      }
    }
    sources[0].favicon = faviconData(d.favicon);
  } else if (Array.isArray(d.hits) && sourceUrl(d.source)) {
    const parent = add(
      d.source,
      `${short(d.provider, 60) || "Public"} index`,
      "index",
      "retrieved",
      d.scope,
    );
    for (const hit of d.hits.slice(0, 20))
      if (hit && typeof hit === "object")
        add(
          hit.url,
          hit.title,
          "lead",
          "listed",
          "Listed by the index. The target page was not retrieved or verified.",
          parent,
        );
  } else if (Array.isArray(d.entries) && sourceUrl(d.url)) {
    const parent = add(d.url, "Published feed", "index", "retrieved");
    for (const entry of d.entries.slice(0, 20))
      if (entry && typeof entry === "object")
        add(entry.url, entry.title, "lead", "listed", entry.summary, parent);
  } else if (sourceUrl(d.requestedUrl) && sourceUrl(d.source)) {
    const parent = add(d.source, "Archive lookup", "index", "retrieved");
    if (d.snapshot && typeof d.snapshot === "object")
      add(
        d.snapshot.url,
        `Archive of ${short(d.requestedUrl, 150)}`,
        "lead",
        "listed",
        "Archive availability was reported. The archived page was not retrieved.",
        parent,
      );
  } else if (
    typeof d.file === "string" &&
    /^[a-f\d]{64}$/i.test(d.sha256 || "")
  ) {
    sources.push({
      id: `file:${d.file}`,
      file: short(d.file, 300),
      title:
        d.analysis === "graphsage"
          ? `${d.synthetic === true ? "SYNTHETIC · " : ""}Transaction model · ${short(d.file, 150)}`
          : short(d.file, 200),
      sha256: d.sha256,
      kind: "file",
      status: "analysed",
      excerpt: short(
        d.text || d.scope,
        d.analysis === "metadata" ? 16000 : 1500,
      ),
    });
  }
  return {
    sources,
    result:
      ["graphsage", "metadata"].includes(d.analysis) && sources.length
        ? short(d.text, 1500)
        : sources.length
          ? `${sources.filter((s) => s.status !== "listed").length} source record(s) read${sources.some((s) => s.status === "listed") ? `; ${sources.filter((s) => s.status === "listed").length} unverified reference(s) listed` : ""}.`
          : "Check completed. No source records were returned.",
  };
}

function pageDetails(
  page: Record<string, unknown>,
  url: string,
): Pick<RunSource, "excerpt" | "reviewNeeded"> {
  const labels: Record<string, string> = {
    wallet: "Wallet address",
    "access-required": "Access required",
    "payment-reference": "Payment reference",
  };
  const findings = Array.isArray(page.findings)
    ? page.findings.slice(0, 40).flatMap((finding: Record<string, unknown>) => {
        if (!finding || typeof finding !== "object") return [];
        const label = labels[String(finding.kind)];
        const findingUrl = sourceUrl(finding.sourceUrl);
        const location = finding.location as
          { line?: unknown; basis?: unknown } | undefined;
        const line = location?.line;
        if (
          !label ||
          finding.reviewStatus !== "needs_review" ||
          !findingUrl ||
          ![url, sourceUrl(page.requestedUrl)].includes(findingUrl) ||
          !Number.isSafeInteger(line) ||
          Number(line) < 1 ||
          (location?.basis !== undefined &&
            location.basis !== "extracted text") ||
          typeof finding.excerpt !== "string"
        )
          return [];
        return [
          `${label} · Needs review\nSource: ${findingUrl}\nExtracted-text line ${line}: ${short(finding.excerpt, 700)}`,
        ];
      })
    : [];
  const extraction =
    page.extraction && typeof page.extraction === "object"
      ? (page.extraction as Record<string, unknown>)
      : {};
  const warnings = Array.isArray(extraction.warnings)
    ? extraction.warnings
        .filter((warning) => typeof warning === "string")
        .slice(0, 8)
        .map((warning) => short(warning, 350))
    : [];
  const nonnegative = (value: unknown) =>
    Number.isSafeInteger(value) && Number(value) >= 0;
  const next = nonnegative(page.nextOffset) ? page.nextOffset : undefined;
  const text = short(page.text, 9000);
  const section =
    nonnegative(page.textOffset) && nonnegative(page.textLength)
      ? `Recorded text offset: ${page.textOffset} of ${page.textLength} characters.${Number.isSafeInteger(page.startLine) && Number(page.startLine) > 0 ? ` Starts at extracted-text line ${page.startLine}.` : ""}${next !== undefined ? ` More text is available at offset ${next}.` : ""}`
      : "";
  const truncated =
    page.textTruncated === true ||
    (typeof page.text === "string" && page.text.length > text.length);
  return {
    excerpt: short(
      [
        findings.length
          ? `Recorded references for review. Their presence does not establish wrongdoing.\n\n${findings.join("\n\n")}`
          : "",
        Array.isArray(page.findings) && page.findings.length > 40
          ? "Review-flag display is limited to 40 entries."
          : "",
        page.findingsTruncated === true
          ? "Review flags are truncated; additional references were omitted from this result."
          : "",
        section,
        truncated ? "The recorded page text is truncated." : "",
        extraction.renderedJavascript === false
          ? "Client-side JavaScript was not executed; dynamically loaded content may be absent."
          : "",
        ...warnings,
        typeof page.hashScope === "string"
          ? `SHA-256 scope: ${short(page.hashScope, 300)}.`
          : "",
        findings.length ||
        section ||
        truncated ||
        warnings.length ||
        Object.keys(extraction).length ||
        page.hashScope
          ? `Retrieved text:\n${text}`
          : text,
      ]
        .filter(Boolean)
        .join("\n\n"),
      18000,
    ),
    reviewNeeded:
      findings.length > 0 ||
      page.findingsTruncated === true ||
      warnings.length > 0 ||
      extraction.javascriptLikely === true ||
      truncated ||
      next !== undefined,
  };
}

function siteReviewResult(
  d: Record<string, unknown>,
): Pick<Activity, "result" | "sources" | "coverage"> {
  const sources: RunSource[] = [];
  const pages = Array.isArray(d.pages) ? d.pages : [];
  for (const page of pages.slice(0, 250)) {
    if (!page || typeof page !== "object") continue;
    const url = sourceUrl(page.url);
    if (
      !url ||
      !["retrieved", "failed", "skipped", "pending"].includes(page.status)
    )
      continue;
    const retrieved =
      page.status === "retrieved" && typeof page.text === "string";
    const parentUrl = sourceUrl(page.parentUrl);
    const details = retrieved
      ? pageDetails(page, url)
      : {
          excerpt: `${page.status === "failed" ? "Retrieval failed" : page.status === "skipped" ? "Skipped" : "Pending"}. This page was not retrieved or verified.${typeof page.reason === "string" ? ` ${short(page.reason, 500)}` : ""}`,
          reviewNeeded: false,
        };
    sources.push({
      id: `url:${url}`,
      url,
      title: short(page.title, 200) || new URL(url).hostname,
      kind: retrieved ? "page" : "lead",
      status: retrieved
        ? "retrieved"
        : page.status === "failed"
          ? "unavailable"
          : "referenced",
      at:
        retrieved &&
        typeof page.fetchedAt === "string" &&
        Number.isFinite(Date.parse(page.fetchedAt))
          ? page.fetchedAt
          : undefined,
      ...details,
      sha256:
        retrieved && /^[a-f\d]{64}$/i.test(page.sha256 || "")
          ? page.sha256
          : undefined,
      favicon: retrieved ? faviconData(page.favicon) : undefined,
      parentId: parentUrl && parentUrl !== url ? `url:${parentUrl}` : undefined,
      parentRelation: parentUrl && parentUrl !== url ? "links to" : undefined,
    });
  }
  const supplied =
    d.coverage && typeof d.coverage === "object"
      ? (d.coverage as Record<string, unknown>)
      : {};
  const count = (key: string, fallback: number) =>
    Number.isSafeInteger(supplied[key]) && Number(supplied[key]) >= 0
      ? Math.min(Number(supplied[key]), 1000000)
      : fallback;
  const retrieved = sources.filter(
    (source) => source.status === "retrieved",
  ).length;
  const failed = sources.filter(
    (source) => source.status === "unavailable",
  ).length;
  const coverage: NonNullable<Activity["coverage"]> = {
    attempted: count("attempted", retrieved + failed),
    retrieved: count("retrieved", retrieved),
    failed: count("failed", failed),
    skipped: count(
      "skipped",
      pages.filter((page) => page?.status === "skipped").length,
    ),
    pending: count(
      "pending",
      pages.filter((page) => page?.status === "pending").length,
    ),
    complete: false,
    stopReason: short(supplied.stopReason, 250) || undefined,
    inventoriesTruncated: count("inventoriesTruncated", 0),
    frontierTruncated: supplied.frontierTruncated === true,
    outputTruncated: supplied.outputTruncated === true,
    omittedRecords: count("omittedRecords", 0),
  };
  const limitations = [
    coverage.inventoriesTruncated
      ? `${coverage.inventoriesTruncated} page link inventories exceeded their limit; additional links were omitted.`
      : "",
    coverage.frontierTruncated
      ? "The discovered-link list reached its limit; additional references were not retained."
      : "",
    coverage.outputTruncated || coverage.omittedRecords
      ? `Output was truncated${coverage.omittedRecords ? `; ${coverage.omittedRecords} page records were omitted` : ""}. Coverage counts include records absent from this display.`
      : "",
  ]
    .filter(Boolean)
    .join(" ");
  return {
    sources,
    coverage,
    result: `Public-page review: ${coverage.retrieved} retrieved, ${coverage.failed} failed, ${coverage.skipped} skipped, ${coverage.pending} pending (${coverage.attempted} attempted). This is a bounded review, not proof of complete website coverage.${coverage.stopReason ? ` Stopped: ${coverage.stopReason}.` : ""}${limitations ? ` ${limitations}` : ""}${pages.length > 250 ? " Source display limited to 250 records." : ""}`,
  };
}

function walletReviewResult(
  d: Record<string, unknown>,
): Pick<Activity, "result" | "sources"> {
  const sources: RunSource[] = [];
  const summary = short(d.text, 12000);
  const references = Array.isArray(d.sources) ? d.sources : [];
  for (const reference of references.slice(0, 12)) {
    if (!reference || typeof reference !== "object") continue;
    const url = sourceUrl(reference.url);
    if (
      !url ||
      typeof reference.fetchedAt !== "string" ||
      !Number.isFinite(Date.parse(reference.fetchedAt))
    )
      continue;
    sources.push({
      id: `url:${url}`,
      url,
      title: `${short(d.network, 30) || "Public"} transaction data`,
      kind: "index",
      status: "retrieved",
      at: reference.fetchedAt,
      sha256: /^[a-f\d]{64}$/i.test(reference.contentSha256 || "")
        ? reference.contentSha256
        : undefined,
      excerpt: summary,
    });
  }
  const failures = Array.isArray(d.failures) ? d.failures : [];
  for (const failure of failures.slice(0, 20)) {
    if (!failure || typeof failure !== "object") continue;
    const url = sourceUrl(failure.url);
    if (!url) continue;
    const reason = `Transaction data could not be used${typeof failure.code === "string" ? ` (${short(failure.code, 80)})` : ""}. This leaves a gap in the review.`;
    const existing = sources.find((source) => source.url === url);
    if (existing) {
      existing.reviewNeeded = true;
      existing.excerpt = `${reason}\n\n${existing.excerpt || ""}`;
    } else {
      sources.push({
        id: `url:${url}`,
        url,
        title: "Unavailable transaction data",
        kind: "lead",
        status: "unavailable",
        reviewNeeded: true,
        excerpt: reason,
      });
    }
  }
  const explorer = sourceUrl(d.explorerUrl);
  if (
    explorer &&
    sources.length &&
    !sources.some((source) => source.url === explorer)
  )
    sources.push({
      id: `url:${explorer}`,
      url: explorer,
      title: `Address explorer · ${short(d.address, 100)}`,
      kind: "lead",
      status: "referenced",
      excerpt:
        "Explorer reference for this public address. The explorer page was not retrieved; transaction data came from the recorded API sources. Address control and ownership remain unverified.",
    });
  const transactions = Array.isArray(d.transactions) ? d.transactions : [];
  function amount(value: unknown) {
    if (!value || typeof value !== "object") return "Not available";
    const a = value as { satoshis?: unknown; btc?: unknown };
    return typeof a.satoshis === "string" &&
      /^-?\d{1,32}$/.test(a.satoshis) &&
      typeof a.btc === "string" &&
      /^-?\d{1,24}(?:\.\d{1,8})?$/.test(a.btc)
      ? `${a.btc} BTC (${a.satoshis} satoshis)`
      : "Not available";
  }
  for (const transaction of transactions.slice(0, 50)) {
    if (
      !transaction ||
      typeof transaction !== "object" ||
      !/^[a-f\d]{64}$/i.test(transaction.txid || "")
    )
      continue;
    const url = sourceUrl(transaction.url);
    const provenance = sourceUrl(transaction.sourceUrl);
    const parent = sources.find(
      (source) => source.status === "retrieved" && source.url === provenance,
    );
    if (!url || !parent) continue;
    const status = transaction.status;
    const confirmed = status?.confirmed === true;
    const confirmations =
      confirmed &&
      Number.isSafeInteger(status.confirmations) &&
      status.confirmations >= 0
        ? ` · ${status.confirmations} confirmations`
        : "";
    const inputs = Array.isArray(transaction.inputs) ? transaction.inputs : [];
    const outputs = Array.isArray(transaction.outputs)
      ? transaction.outputs
      : [];
    const details = (items: Record<string, unknown>[], kind: string) =>
      items
        .slice(0, 20)
        .map(
          (item, index) =>
            `${kind} ${index}: ${short(item?.address, 120) || "Address unavailable"} · ${amount(item?.amount)}`,
        );
    sources.push({
      id: `url:${url}`,
      url,
      title: `Transaction · ${transaction.txid.slice(0, 12)}…`,
      kind: "lead",
      status: "referenced",
      at: parent.at,
      parentId: parent.id,
      parentRelation: "lists",
      excerpt: [
        `Transaction record from ${provenance}. The linked explorer page was not retrieved.`,
        `Transaction ID: ${transaction.txid}`,
        `Status: ${confirmed ? "Confirmed" : "Unconfirmed"}${confirmations}`,
        `Address received: ${amount(transaction.addressReceived)}`,
        `Address spent: ${amount(transaction.addressSpent)}`,
        `Address net: ${amount(transaction.addressNet)}`,
        `Transaction fee: ${amount(transaction.fee)}`,
        ...details(inputs, "Input"),
        ...details(outputs, "Output"),
        inputs.length > 20 || outputs.length > 20
          ? "Input/output display limited to 20 entries each."
          : "",
        "Input/output co-occurrence does not establish a sender-to-recipient transfer or common ownership. Exchange attribution requires a cited provider record; KYC information is not public wallet data.",
      ]
        .filter(Boolean)
        .join("\n\n"),
    });
  }
  return {
    sources,
    result: `${short(d.text, 1300) || "Public transaction review completed."} ${sources.filter((source) => source.status === "retrieved").length} API source(s) retrieved; ${sources.filter((source) => source.parentId).length} transaction reference(s) recorded. Full-history coverage is not established.`,
  };
}

export function recordActivity(list: Activity[], entry: Activity) {
  const previous = list.find((step) => step.id === entry.id);
  if (previous) Object.assign(previous, entry, { at: previous.at || entry.at });
  else list.push(entry);
  list.sort((a, b) => (a.at || "").localeCompare(b.at || ""));
  // Bound persisted/public history, with an explicit notice on the owning run.
  return list.length > 300 ? (list.splice(0, list.length - 300), true) : false;
}

export function publicUpdate(
  list: Activity[],
  id: string,
  text: string,
  at: string,
) {
  return recordActivity(list, {
    id,
    label: "Progress update",
    kind: "update",
    status: "completed",
    at,
    detail: text.slice(0, 8000),
  });
}
