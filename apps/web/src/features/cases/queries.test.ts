import { describe, expect, it } from "vitest";

import type { ApiCase } from "@/lib/api/cases";

import { CaseContractError, mapCaseSummary } from "./queries";

const BASE_CASE: ApiCase = {
  id: "4d61f3aa-b46e-4ed2-b516-e91ec5930abc",
  case_code: "CHD-2026-001",
  title: "Synthetic narcotics case",
  status: "OPEN",
  sensitivity: "STANDARD",
  owner_user_id: "2b18f363-8fc0-44aa-8312-7f4792e663af",
  source_authority_summary: "Authorized synthetic fixture for investigator training",
  created_at: "2026-08-17T09:30:00+05:30",
  updated_at: "2026-08-17T10:45:00+05:30",
  closed_at: null,
};

describe("mapCaseSummary", () => {
  it("maps the transport case into the retained UI shape and normalizes time", () => {
    expect(mapCaseSummary(BASE_CASE)).toEqual({
      caseCode: BASE_CASE.case_code,
      collectionStatus: "Authority recorded",
      createdAt: "2026-08-17T04:00:00.000Z",
      id: BASE_CASE.id,
      title: BASE_CASE.title,
      status: "OPEN",
      sensitivity: "STANDARD",
      sourceClass: "SYNTHETIC",
      sourceAuthority: BASE_CASE.source_authority_summary,
      owner: BASE_CASE.owner_user_id,
      evidenceCount: 0,
      pendingReviews: 0,
      openAlerts: 0,
      processStage: "Collection",
      updatedAt: "2026-08-17T05:15:00.000Z",
    });
  });

  it("maps an explicit research-archive authority summary", () => {
    expect(
      mapCaseSummary({
        ...BASE_CASE,
        source_authority_summary: "Research archive material authorized for controlled review",
      }).sourceClass,
    ).toBe("RESEARCH_ARCHIVE");
  });

  it("keeps normally worded authorized source metadata visible instead of rejecting the case", () => {
    expect(
      mapCaseSummary({
        ...BASE_CASE,
        source_authority_summary: "Authorized case material received under court order 26-481",
      }),
    ).toMatchObject({
      sourceClass: "AUTHORIZED_SOURCE",
      sourceAuthority: "Authorized case material received under court order 26-481",
      collectionStatus: "Authority recorded",
      processStage: "Collection",
    });
  });

  it.each([
    ["status", { status: "PAUSED" }],
    ["sensitivity", { sensitivity: "SECRET" }],
    ["updated timestamp", { updated_at: "not-a-date" }],
  ])("rejects an unsupported %s instead of silently coercing it", (_label, patch) => {
    expect(() => mapCaseSummary({ ...BASE_CASE, ...patch } as ApiCase)).toThrow(CaseContractError);
  });
});
