import { describe, expect, it } from "vitest";
import { can, writable } from "./permissions";
import type { S } from "./types";
const account = (role: S<"UserMe">["global_role"]) =>
  ({ global_role: role }) as S<"UserMe">;
const record = (
  role: S<"Case">["my_role"],
  status: S<"Case">["status"] = "OPEN",
) => ({ my_role: role, status }) as S<"Case">;
describe("case UI permissions", () => {
  it("permits analyst operations without widening policy/export access", () => {
    expect(writable(account("INVESTIGATOR"), record("ANALYST"))).toBe(true);
    expect(can(account("INVESTIGATOR"), record("ANALYST"), "manage")).toBe(
      false,
    );
    expect(can(account("INVESTIGATOR"), record("ANALYST"), "export")).toBe(
      false,
    );
  });
  it("respects global viewer ceilings and inaccessible case membership", () => {
    expect(writable(account("VIEWER"), record("OWNER"))).toBe(false);
    expect(writable(account("INVESTIGATOR"), record("VIEWER"))).toBe(false);
    expect(writable(account("INVESTIGATOR"), record(null))).toBe(false);
  });
  it("keeps immutable closed cases viewable and restricts archive to owners", () => {
    expect(writable(account("ADMIN"), record("OWNER", "CLOSED"))).toBe(false);
    expect(
      can(account("INVESTIGATOR"), record("ANALYST", "CLOSED"), "write"),
    ).toBe(true);
    expect(can(account("INVESTIGATOR"), record("LEAD"), "archive")).toBe(false);
    expect(can(account("INVESTIGATOR"), record("OWNER"), "archive")).toBe(true);
  });
});
