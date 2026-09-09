import { afterEach, beforeEach, expect, test } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import {
  continueNetra,
  NETRA_MAX_TURNS,
  NETRA_TIME_LIMIT_MS,
  readNativeGoal,
} from "./netra";
import { cliArgs } from "./codex";

let directory: string;
beforeEach(async () => {
  directory = await mkdtemp(path.join(tmpdir(), "SYNTHETIC-netra-"));
});
afterEach(async () => {
  await rm(directory, { recursive: true, force: true });
});

test("native goal reads are session-scoped, current and read-only", async () => {
  const db = new DatabaseSync(path.join(directory, "goals_1.sqlite"));
  const id = "00000000-0000-4000-8000-000000000001";
  const other = "00000000-0000-4000-8000-000000000002";
  const since = "2026-09-08T10:00:00.000Z";
  db.exec(
    "CREATE TABLE thread_goals (thread_id TEXT PRIMARY KEY, objective TEXT, status TEXT, tokens_used INTEGER, updated_at_ms INTEGER)",
  );
  const insert = db.prepare("INSERT INTO thread_goals VALUES (?, ?, ?, ?, ?)");
  insert.run(id, "SYNTHETIC scoped review", "active", 50, Date.parse(since));
  insert.run(
    other,
    "SYNTHETIC different case",
    "complete",
    200,
    Date.parse(since),
  );
  expect(await readNativeGoal(id, since, directory)).toEqual({
    objective: "SYNTHETIC scoped review",
    status: "active",
    tokensUsed: 50,
  });
  expect(
    await readNativeGoal(id, "2026-09-08T11:00:00Z", directory),
  ).toBeUndefined();
  expect(
    await readNativeGoal("invalid' OR 1=1", since, directory),
  ).toBeUndefined();
  db.prepare(
    "UPDATE thread_goals SET status = 'complete' WHERE thread_id = ?",
  ).run(id);
  expect((await readNativeGoal(id, since, directory))?.status).toBe("complete");
  expect(
    db.prepare("SELECT COUNT(*) AS count FROM thread_goals").get()?.count,
  ).toBe(2);
  db.close();
});

test("missing native goal state never becomes a simulated active goal", async () => {
  expect(
    await readNativeGoal(
      "00000000-0000-4000-8000-000000000001",
      new Date().toISOString(),
      directory,
    ),
  ).toBeUndefined();
  expect(continueNetra(undefined, false, 0)).toBe(false);
});

test("only an active goal continues within its stop, time and turn limits", () => {
  const goal = { status: "active" as const, turns: 1 };
  expect(continueNetra(goal, false, 100)).toBe(true);
  expect(continueNetra(goal, true, 100)).toBe(false);
  expect(continueNetra(goal, false, NETRA_TIME_LIMIT_MS)).toBe(false);
  expect(continueNetra({ ...goal, turns: NETRA_MAX_TURNS }, false, 0)).toBe(
    false,
  );
  for (const status of [
    "complete",
    "blocked",
    "paused",
    "unavailable",
    "limit_reached",
  ] as const)
    expect(continueNetra({ ...goal, status }, false, 0)).toBe(false);
});

test("Netra enables real goal tools while retaining read-only execution and specialist limits", () => {
  const args = cliArgs("SYNTHETIC-session", "netra");
  expect(args).toContain("features.goals=true");
  expect(cliArgs(undefined, "normal")).toContain("features.goals=false");
  expect(args).toContain('permissions.research.extends=":read-only"');
  expect(args).toContain("agents.max_concurrent_threads_per_session=2");
  expect(args).toContain(
    'agents.darkweb_investigator.nickname_candidates=["Dark Web Investigator"]',
  );
  expect(args).toContain(
    'agents.evidence_reviewer.nickname_candidates=["Evidence Reviewer"]',
  );
  expect(args).toContain('model_reasoning_effort="high"');
  expect(args.slice(-3)).toEqual(["resume", "SYNTHETIC-session", "-"]);
});
