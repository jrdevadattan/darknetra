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
      /osint\.mjs["']?\s+(?:page|feed|wayback|apify-page|image-metadata)\s+["']?(https?:\/\/[^\s"'<>]+)/,
    )?.[1],
  );
}

export function commandLabel(command = "") {
  const helper = command.match(/osint\.mjs["']?\s+([\w-]+)/)?.[1];
  const labels: Record<string, string> = {
    page: "Reading a source",
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
): Pick<Activity, "result" | "sources"> {
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
    if (d.analysis === "metadata" && /^[a-f\d]{64}$/i.test(d.sha256 || "")) {
      sources[0].sha256 = d.sha256;
      sources[0].excerpt = short(d.text, 16000);
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
