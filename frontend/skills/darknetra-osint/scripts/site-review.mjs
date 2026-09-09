import { parsePage } from "./page.mjs";
import { publicUrl } from "./public-url.mjs";
import { setTimeout as delay } from "node:timers/promises";

const DEADLINE = 180000,
  DEPTH = 4,
  FRONTIER = 250;
const fail = (message) =>
  Object.assign(new Error(message), { code: "VALIDATION" });
function skipReason(url, origin) {
  if (url.origin !== origin)
    return "External reference; not included in this site's public-page collection.";
  let path;
  try {
    path = decodeURIComponent(url.pathname);
  } catch {
    return "Malformed URL path.";
  }
  if (
    /(?:^|[\/._-])(?:login|signin|sign-in|signup|sign-up|register|logout|logoff|account|cart|checkout|delete|remove|unsubscribe|submit|buy|bid)(?:$|[\/._-])/i.test(
      path,
    )
  )
    return "Access or action page; no account creation, login, form submission or transaction attempted.";
  if (
    [...url.searchParams.keys()].some((key) =>
      /^(?:action|do|cmd|token|access_token|session|password|auth)$/i.test(key),
    )
  )
    return "Action or access parameter; not followed automatically.";
  if (
    /\.(?:jpe?g|png|gif|webp|svg|ico|mp4|mp3|wav|zip|rar|7z|exe|pdf|docx?|xlsx?|pptx?)(?:$)/i.test(
      path,
    )
  )
    return "Media or document reference; use the relevant supplied-file or image workflow if needed.";
}

export async function siteReview(
  value,
  count = 30,
  { reader, now = Date.now, pause = () => delay(500) } = {},
) {
  const limit = Number(count);
  if (!Number.isInteger(limit) || limit < 1 || limit > 60)
    throw fail("Site review page limit must be 1–60.");
  if (typeof reader !== "function")
    throw fail("A public-page reader is required.");
  const seed = publicUrl(value),
    started = now(),
    signal = AbortSignal.timeout(DEADLINE);
  let origin = seed.origin,
    attempted = 0,
    frontierTruncated = false,
    inventoriesTruncated = 0,
    duplicateLinks = 0,
    stopReason = "discovered_queue_exhausted";
  const queue = [{ url: seed.href, parentUrl: null, depth: 0 }],
    seen = new Set([seed.href]),
    retrieved = new Set(),
    pages = [],
    variants = new Map();
  while (queue.length) {
    if (now() - started >= DEADLINE || signal.aborted) {
      stopReason = "time_limit";
      break;
    }
    if (attempted >= limit) {
      stopReason = "page_limit";
      break;
    }
    const item = queue.shift();
    if (item.depth > DEPTH) {
      pages.push({
        ...item,
        status: "pending",
        reason:
          "Depth limit; continue from this reference in a later scoped review.",
      });
      continue;
    }
    attempted++;
    try {
      const source = await reader(
        item.url,
        0,
        seed.hostname.endsWith(".onion"),
        undefined,
        false,
        {
          ...(item.depth === 0
            ? {
                allowedHostname: seed.hostname,
                requireHttps: seed.protocol === "https:",
              }
            : { allowedOrigin: origin }),
          signal,
        },
      );
      const finalUrl = publicUrl(source.url);
      if (item.depth === 0) {
        if (
          finalUrl.hostname !== seed.hostname ||
          (seed.protocol === "https:" && finalUrl.protocol !== "https:")
        )
          throw fail("The initial page redirected outside the supplied site.");
        origin = finalUrl.origin;
      } else if (finalUrl.origin !== origin)
        throw fail("The page redirected outside this site's scope.");
      if (finalUrl.href !== item.url && retrieved.has(finalUrl.href)) {
        pages.push({
          ...item,
          status: "skipped",
          reason: "Redirect reached a previously recorded page.",
        });
        continue;
      }
      seen.add(finalUrl.href);
      retrieved.add(finalUrl.href);
      for (let i = queue.length - 1; i >= 0; i--) {
        if (queue[i].url === finalUrl.href) {
          queue.splice(i, 1);
          duplicateLinks++;
        }
      }
      const parsed = parsePage(source, { textLimit: 6000, linkLimit: 500 });
      if (parsed.linkSummary.truncated) inventoriesTruncated++;
      pages.push({
        ...item,
        requestedUrl: item.url,
        url: parsed.url,
        status: "retrieved",
        title: parsed.title,
        fetchedAt: parsed.fetchedAt,
        sha256: parsed.sha256,
        hashScope: parsed.hashScope,
        text: parsed.text,
        textOffset: parsed.textOffset,
        textTruncated: parsed.textTruncated,
        textLength: parsed.textLength,
        nextOffset: parsed.nextOffset,
        startLine: parsed.startLine,
        findings: parsed.findings.slice(0, 12),
        findingsTruncated: parsed.findings.length > 12,
        access: parsed.access,
        extraction: parsed.extraction,
      });
      // A challenge response is observable, but its links are not a path around the gate.
      if (parsed.access.challengeMentioned) continue;
      for (const link of parsed.links) {
        if (seen.has(link.url)) {
          duplicateLinks++;
          continue;
        }
        if (pages.length + queue.length >= FRONTIER) {
          frontierTruncated = true;
          break;
        }
        const target = publicUrl(link.url),
          next = {
            url: target.href,
            parentUrl: parsed.url,
            depth: item.depth + 1,
            title: link.title,
          };
        seen.add(target.href);
        const reason = skipReason(target, origin);
        if (reason) {
          pages.push({ ...next, status: "skipped", reason });
          continue;
        }
        const pathKey = target.origin + target.pathname,
          variantsSeen = variants.get(pathKey) || 0;
        if (variantsSeen >= 5) {
          pages.push({
            ...next,
            status: "pending",
            reason: "Query variant limit; further pagination remains unread.",
          });
          continue;
        }
        variants.set(pathKey, variantsSeen + 1);
        queue.push(next);
      }
    } catch (error) {
      pages.push({
        ...item,
        status: "failed",
        reason:
          /^(?:VALIDATION|POLICY_DENIED|UPSTREAM_UNAVAILABLE|UNSUPPORTED_TYPE|SIZE_LIMIT|ACCESS_DENIED|RATE_LIMITED|NOT_FOUND)$/.test(
            error.code || "",
          )
            ? String(error.message).slice(0, 500)
            : "The public page could not be read within the available time.",
      });
      if (["ACCESS_DENIED", "RATE_LIMITED"].includes(error.code)) {
        stopReason =
          error.code === "RATE_LIMITED" ? "rate_limited" : "access_denied";
        break;
      }
    }
    if (
      queue.length &&
      attempted < limit &&
      now() - started < DEADLINE &&
      !signal.aborted
    )
      await pause();
  }
  pages.push(
    ...queue.map((item) => ({
      ...item,
      status: "pending",
      reason: `Collection stopped (${stopReason}); this linked page remains unread.`,
    })),
  );
  const counts = Object.fromEntries(
    ["retrieved", "failed", "skipped", "pending"].map((status) => [
      status,
      pages.filter((p) => p.status === status).length,
    ]),
  );
  const coverage = {
    attempted,
    ...counts,
    stopReason,
    complete: false,
    inventoriesTruncated,
    frontierTruncated,
    duplicateLinks,
    partialTextPages: pages.filter((p) => p.textTruncated).length,
    limits: {
      pages: limit,
      depth: DEPTH,
      seconds: DEADLINE / 1000,
      frontier: FRONTIER,
    },
    scope:
      "Public explicit same-origin links only. No account creation, login, form submission, JavaScript rendering or hidden-page discovery. Queue exhaustion is not proof of whole-site coverage.",
  };
  let omittedRecords = 0;
  // Preserve a valid, bounded JSON result for the CLI/UI; never silently lose output.
  while (Buffer.byteLength(JSON.stringify(pages)) > 850000) {
    pages.pop();
    omittedRecords++;
  }
  if (omittedRecords) {
    coverage.outputTruncated = true;
    coverage.omittedRecords = omittedRecords;
  }
  return {
    analysis: "site-review",
    url: seed.href,
    title: "Public website review",
    fetchedAt: new Date().toISOString(),
    coverage,
    pages,
    text: `${counts.retrieved} public pages read; ${counts.failed} failed; ${counts.skipped} skipped; ${counts.pending} pending. ${coverage.partialTextPages} pages have further text sections. Stop: ${stopReason}. This is a bounded source review, not complete website coverage. Review flags identify quoted leads, not confirmed wrongdoing.`,
  };
}
