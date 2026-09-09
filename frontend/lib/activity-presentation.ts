import type { Activity } from "./chat-types";
import { commandLabel, commandTarget, sourceUrl } from "./run-activity";

export type ActivityFilter = "all" | "working" | "attention";

// Presentation only: older commands remain intact in the saved activity record.
export function activityPresentation(step: Activity) {
  const detail = step.detail?.trim() || "";
  const technical =
    step.kind !== "update" &&
    /^(?:\/bin\/(?:ba)?sh\b|(?:bash|sh|cmd|powershell|pwsh)(?:\.exe)?\s|(?:node|python[\d.]*)\s.*(?:osint\.mjs|\.py\b))/i.test(
      detail,
    );
  const url =
    sourceUrl(step.targetUrl) ||
    (technical ? commandTarget(detail) : undefined) ||
    step.sources?.map((source) => sourceUrl(source.url)).find(Boolean);
  const source = step.sources?.find((source) => sourceUrl(source.url) === url);
  const title = technical ? commandLabel(detail) : step.label;
  const state = ["running", "in_progress", "pending"].includes(step.status)
    ? "working"
    : ["failed", "error", "unverified", "stopped"].includes(step.status) ||
        /^This check could not be completed/.test(step.result || "") ||
        step.sources?.some(
          (source) => source.status === "unavailable" || source.reviewNeeded,
        ) ||
        !!(
          step.coverage &&
          (step.coverage.failed ||
            step.coverage.skipped ||
            step.coverage.pending ||
            step.coverage.inventoriesTruncated ||
            step.coverage.frontierTruncated ||
            step.coverage.outputTruncated ||
            step.coverage.omittedRecords)
        )
      ? "attention"
      : ["completed", "done"].includes(step.status)
        ? "complete"
        : "neutral";
  const status =
    state === "working"
      ? "Working"
      : state === "attention"
        ? step.status === "stopped"
          ? "Stopped"
          : "Needs attention"
        : state === "complete"
          ? "Completed"
          : "Recorded";
  const host = url ? new URL(url).hostname.replace(/^www\./, "") : "";
  const subtitle =
    source?.title && source.title !== host
      ? source.title
      : host ||
        (step.kind === "update"
          ? "Investigator update"
          : technical
            ? "Case material review"
            : step.result || detail);
  const start = step.at ? Date.parse(step.at) : NaN;
  const end = step.finishedAt ? Date.parse(step.finishedAt) : NaN;
  const seconds =
    Number.isFinite(start) && Number.isFinite(end) && end >= start
      ? (end - start) / 1000
      : undefined;
  const duration =
    seconds === undefined
      ? undefined
      : seconds < 60
        ? `${seconds.toFixed(1)}s`
        : `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  return {
    title,
    url,
    source,
    technical,
    subtitle,
    state,
    status,
    duration,
    at: Number.isFinite(start) ? step.at : undefined,
  };
}

export function matchesActivity(
  step: Activity,
  filter: ActivityFilter,
  query: string,
  investigator = "",
) {
  const view = activityPresentation(step);
  if (filter !== "all" && view.state !== filter) return false;
  return `${view.title} ${view.subtitle} ${view.url || ""} ${step.detail || ""} ${step.result || ""} ${step.sources?.map((s) => `${s.title} ${s.url || ""}`).join(" ") || ""} ${investigator}`
    .toLowerCase()
    .includes(query.trim().toLowerCase());
}
