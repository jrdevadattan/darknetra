import { describe, expect, it } from "vitest";

import { buildSidebarItems } from "./sidebar-items";

function titlesFor(roles: Parameters<typeof buildSidebarItems>[0]): string[] {
  return buildSidebarItems(roles).flatMap((group) => [
    ...group.items.map((item) => item.title),
    ...group.items.flatMap((item) => item.subItems?.map((subItem) => subItem.title) ?? []),
  ]);
}

describe("sidebar role filtering", () => {
  it("shows administration to administrators", () => {
    expect(titlesFor(["ADMIN"])).toContain("Administration");
    expect(titlesFor(["ADMIN"])).toContain("Roles & Permissions");
  });

  it("shows audit/health but not administration to auditors", () => {
    const titles = titlesFor(["AUDITOR"]);
    expect(titles).toContain("Audit");
    expect(titles).toContain("System Health");
    expect(titles).not.toContain("Administration");
    expect(titles).not.toContain("Roles & Permissions");
  });
});
