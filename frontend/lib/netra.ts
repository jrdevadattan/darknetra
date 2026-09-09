import { readdir } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import type { NetraGoal } from "./chat-types";

export const NETRA_MAX_TURNS = 6;
export const NETRA_TIME_LIMIT_MS = 600_000;

export const NETRA_INSTRUCTIONS = `
NETRA MODE IS ON FOR THIS REQUEST. You are the Netra Case Lead.
Purpose: investigate public reports and case-relevant websites that advertise or solicit illicit trade, using public surface-web sources and relevant Tor sources. Collect source-backed observations useful to the current investigation. Never promise to find every website, prove a completed transaction from advertising, or identify a buyer or seller from an alias alone.

Read the darknetra-osint skill and its references/netra.md. Use the native create_goal/get_goal/update_goal tools that back /goal. Do not type /goal into a shell or merely say a goal was created. First inspect get_goal. If no unfinished goal exists, explicitly create a concise, bounded goal for this user's current case and scope. If an unfinished goal exists, continue it under the current user's scope; do not silently expand to unrelated investigations. The goal ends when the scoped sources have been checked, specialist findings reviewed, contradictions and gaps recorded, and a cited report delivered. If the request lacks any useful category, reference, region or case context, ask for the needed scope before research; do not create an unlimited internet-wide hunt.

Delegate independent supported research to surface_investigator and darkweb_investigator using actual native subagents. Give each the current scope, exact checks and source requirements; at most two active concurrently. A lane without relevant sources should report that limitation, not browse unrelated targets. After their reports, delegate a distinct corroboration review to evidence_reviewer, supplying their cited observations and disputed points. The reviewer checks original sources and contradictions, not just the other agents' prose. Do not invent subagents or report completion until their actual results arrive. Keep public progress and source-helper output available to the activity timeline.

Use actual native goal state: mark complete only after the scoped review and report are finished. A report may find no verified match; say what was searched and distinguish no supported observation from failed retrieval. Do not mark complete just because a turn ends. If more independent checks remain and are possible, leave the goal active for the harness to continue. If human records, source access or scope are required, explain exactly what is missing and follow the native goal tool's blocked-status rules. Never manufacture findings to achieve a goal. This app allows at most six CLI turns and ten minutes per Netra request; return a useful partial report before those limits when possible. A stopped or limited run is not a completed investigation.

All existing read-only, case-isolation, citation, tool and provider rules still apply. Netra does not create monitoring schedules unless separately requested. Apify remains a backup. The ML output remains supplementary. A source is evidence of what it actually published, not proof that the advertised conduct occurred. Do not create procurement guides, vendor recommendations, transaction instructions or inventories optimized for obtaining illegal goods. Keep the report focused on source observations, dates, provenance, corroboration, uncertainty and case-specific next leads.
`;

export const NETRA_CONTINUATION =
  "Continue the active Netra goal for this same case and the user's latest scope. Inspect get_goal, review actual specialist results and complete the next useful check. Keep all original limits. Do not create another goal or a monitoring schedule. If the review is complete, deliver the cited report and mark the native goal complete. If blocked, state the precise missing source or record; do not repeat failed checks without a changed condition.";

// codex exec 0.153.4 does not emit goal events in JSONL. Read only its native
// persisted goal row for this exact session; never create/update goal state here.
// This adapter is intentionally tied to the pinned CLI schema and fails closed.
export async function readNativeGoal(
  sessionId: string,
  since: string,
  root = process.env.CODEX_HOME || path.join(homedir(), ".codex"),
): Promise<Omit<NetraGoal, "turns"> | undefined> {
  if (!/^[a-f0-9-]{36}$/i.test(sessionId)) return;
  try {
    const { DatabaseSync } = await import("node:sqlite");
    const names = (await readdir(root))
      .filter((name) => /^goals_\d+\.sqlite$/.test(name))
      .sort((a, b) => Number(b.match(/\d+/)![0]) - Number(a.match(/\d+/)![0]));
    // Goals have their own database, separate from state and thread history.
    if (!names[0]) return;
    const database = new DatabaseSync(path.join(root, names[0]), {
      readOnly: true,
    });
    try {
      const row = database
        .prepare(
          "SELECT objective, status, tokens_used, updated_at_ms FROM thread_goals WHERE thread_id = ?",
        )
        .get(sessionId);
      if (
        !row ||
        typeof row.updated_at_ms !== "number" ||
        row.updated_at_ms < Date.parse(since) - 1000
      )
        return;
      const statuses: Record<string, NetraGoal["status"]> = {
        active: "active",
        complete: "complete",
        blocked: "blocked",
        paused: "paused",
        budget_exceeded: "limit_reached",
        budget_reached: "limit_reached",
      };
      const status = statuses[String(row.status)];
      if (!status || typeof row.objective !== "string") return;
      return {
        status,
        objective: row.objective.slice(0, 4000),
        tokensUsed:
          typeof row.tokens_used === "number" ? row.tokens_used : undefined,
      };
    } finally {
      database.close();
    }
  } catch {
    return;
  }
}

export function continueNetra(
  goal: NetraGoal | undefined,
  stopped: boolean,
  elapsedMs: number,
) {
  return (
    !stopped &&
    goal?.status === "active" &&
    goal.turns < NETRA_MAX_TURNS &&
    elapsedMs < NETRA_TIME_LIMIT_MS
  );
}
