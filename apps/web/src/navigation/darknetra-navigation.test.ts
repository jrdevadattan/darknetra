import { describe, expect, it } from "vitest";

import {
  CASE_NAVIGATION,
  DARKNETRA_NAVIGATION,
  canSeeNavigationItem,
  type DarknetraRole,
} from "./darknetra-navigation";

const flattenHrefs = (items: typeof DARKNETRA_NAVIGATION): string[] =>
  items.flatMap((item) => [item.href, ...(item.children?.map((child) => child.href) ?? [])]);

describe("DARKNETRA navigation contract", () => {
  it("contains approved global routes and no rejected showcase routes", () => {
    const hrefs = flattenHrefs(DARKNETRA_NAVIGATION);
    expect(hrefs).toEqual(
      expect.arrayContaining([
        "/dashboard",
        "/cases",
        "/intelligence/trends",
        "/admin/roles",
        "/audit",
        "/system/health",
      ]),
    );
    expect(hrefs.join(" ")).not.toMatch(/ecommerce|crm|finance|academy|mail|calendar|chat/i);
  });

  it("contains all nine case tabs", () => {
    expect(CASE_NAVIGATION.map((item) => item.title)).toEqual([
      "Overview",
      "Evidence",
      "Entities",
      "Activity Candidates",
      "Link Analysis",
      "NarcoGraph",
      "Timeline",
      "Alerts",
      "Reports",
    ]);
  });

  it("applies role visibility using any-role matching", () => {
    const adminOnly = { roles: ["ADMIN"] as DarknetraRole[] };
    expect(canSeeNavigationItem(adminOnly, ["ADMIN"])).toBe(true);
    expect(canSeeNavigationItem(adminOnly, ["AUDITOR"])).toBe(false);
    expect(canSeeNavigationItem({}, ["AUDITOR"])).toBe(true);
  });
});
