import { describe, expect, it } from "vitest";
import { buildRequest, parseSseFrames } from "./api";

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

describe("parseSseFrames", () => {
  it("keeps the event id so a reconnect can use Last-Event-ID", () => {
    expect(parseSseFrames("id: 18\nevent: activity.updated\ndata: {\"id\":\"tool-1\"}\n\n")).toEqual([
      { id: "18", event: "activity.updated", data: { id: "tool-1" } },
    ]);
  });
});
