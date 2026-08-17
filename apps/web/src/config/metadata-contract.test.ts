import { describe, expect, it } from "vitest";

import { ROOT_METADATA } from "./root-metadata";

describe("root metadata", () => {
  it("uses the approved DARKNETRA metadata", () => {
    expect(ROOT_METADATA.title).toBe("DARKNETRA — Investigator Intelligence");
    expect(ROOT_METADATA.description).toBe("Evidence-first narcotics intelligence for authorized investigators.");
  });
});
