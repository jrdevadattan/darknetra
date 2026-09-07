import { describe, expect, it } from "vitest";
import { buildRequest } from "./api";

describe("buildRequest", () => {
  it("adds the CSRF header and JSON body to a case message mutation", () => {
    const request = buildRequest("POST", { content: "Review E-0007" }, "token-123");

    expect(request.credentials).toBe("include");
    expect(request.headers).toMatchObject({
      "Content-Type": "application/json",
      "X-CSRF-Token": "token-123",
    });
    expect(request.body).toBe('{"content":"Review E-0007"}');
  });

  it("does not add a CSRF header to a case read", () => {
    const request = buildRequest("GET", undefined, "token-123");

    expect(request.headers).not.toHaveProperty("X-CSRF-Token");
    expect(request.body).toBeUndefined();
  });
});
