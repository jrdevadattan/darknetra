import { expect, test } from "vitest";
import { activityPresentation, matchesActivity } from "./activity-presentation";
import type { Activity } from "./chat-types";

test("legacy commands get readable titles and safe targets without changing saved records", () => {
  const step: Activity = {
    id: "SYNTHETIC-old",
    label: "Checking case material",
    status: "completed",
    detail: `/bin/bash -lc "node .agents/skills/darknetra-osint/scripts/osint.mjs page 'https://example.com/SYNTHETIC'"`,
  };
  const before = JSON.stringify(step);
  expect(activityPresentation(step)).toMatchObject({
    title: "Reading a source",
    url: "https://example.com/SYNTHETIC",
    subtitle: "example.com",
    technical: true,
  });
  expect(JSON.stringify(step)).toBe(before);
  expect(step.sources).toBeUndefined();
  expect(
    activityPresentation({
      ...step,
      targetUrl: "javascript:alert(1)",
      detail: "",
    }).url,
  ).toBeUndefined();
  expect(
    activityPresentation({
      ...step,
      detail: "node osint.mjs page 'https://user:secret@example.com/'",
    }).url,
  ).toBeUndefined();
  expect(
    activityPresentation({
      ...step,
      kind: "update",
      detail:
        "Reviewing a reference to osint.mjs page in the supplied document.",
    }).technical,
  ).toBe(false);
});

test("unsuccessful results stay visible as attention even when their command completed", () => {
  const step: Activity = {
    id: "SYNTHETIC-failure",
    label: "Reading a source",
    status: "completed",
    result:
      "This check could not be completed (NETWORK_REQUIRED). This does not establish that there are no matches.",
  };
  expect(activityPresentation(step).state).toBe("attention");
  expect(matchesActivity(step, "attention", "", "Research Analyst")).toBe(true);
  expect(matchesActivity(step, "working", "")).toBe(false);
  expect(activityPresentation({ ...step, status: "stopped" }).status).toBe(
    "Stopped",
  );
  expect(
    activityPresentation({
      ...step,
      result: "A listed reference was recorded.",
    }).status,
  ).toBe("Completed");
});

test("filters find sources and investigators and missing or invalid times produce no invented duration", () => {
  const step: Activity = {
    id: "SYNTHETIC-read",
    label: "Reading a source",
    status: "running",
    at: "2026-09-08T10:00:00Z",
    sources: [
      {
        id: "SYNTHETIC-source",
        title: "SYNTHETIC public bulletin",
        url: "https://example.org/reference",
        kind: "page",
        status: "retrieved",
        favicon: "data:image/png;base64,U1lOVEhFVElD",
      },
    ],
  };
  expect(matchesActivity(step, "working", "EXAMPLE.ORG")).toBe(true);
  expect(
    matchesActivity(step, "all", "research analyst", "Research Analyst"),
  ).toBe(true);
  expect(matchesActivity(step, "all", "missing site")).toBe(false);
  expect(activityPresentation(step).source?.favicon).toBe(
    step.sources![0].favicon,
  );
  expect(activityPresentation(step).duration).toBeUndefined();
  expect(
    activityPresentation({ ...step, finishedAt: "2026-09-08T10:01:05Z" })
      .duration,
  ).toBe("1m 5s");
  expect(
    activityPresentation({ ...step, at: "invalid", finishedAt: "invalid" }).at,
  ).toBeUndefined();
});
