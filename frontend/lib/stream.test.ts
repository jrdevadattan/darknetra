import { describe, expect, it } from "vitest";
import { EventParser, terminal } from "./stream";

describe("durable SSE framing", () => {
  it("reassembles every possible boundary in CRLF frames, including a heartbeat", () => {
    const input =
      ': ping\r\n\r\nid: 12\r\nevent: activity.updated\r\ndata: {"summary":"SYNTHETIC — स्थिति"}\r\n\r\nid: 13\r\nevent: run.finished\r\ndata: {"status":"DONE"}\r\n\r\n';
    for (let at = 0; at <= input.length; at++) {
      const parser = new EventParser();
      const frames = [
        ...parser.push(input.slice(0, at)),
        ...parser.push(input.slice(at)),
      ];
      expect(frames).toEqual([
        {
          id: 12,
          event: "activity.updated",
          data: { summary: "SYNTHETIC — स्थिति" },
        },
        { id: 13, event: "run.finished", data: { status: "DONE" } },
      ]);
    }
  });
  it("handles LF, multiline JSON, comments, and multiple frames", () => {
    const parser = new EventParser();
    expect(
      parser.push(
        'id: 1\ndata: {\ndata: "ok": true}\n\nid: 2\nevent: run.started\ndata: {}\n\n',
      ),
    ).toEqual([
      { id: 1, event: "message", data: { ok: true } },
      { id: 2, event: "run.started", data: {} },
    ]);
    expect(parser.push(": heartbeat\n\nevent: no-id\ndata: {}\n\n")).toEqual(
      [],
    );
  });
  it("rejects malformed or unbounded event payloads for reconnect", () => {
    expect(() => new EventParser().push("id: 1\ndata: nope\n\n")).toThrow();
    expect(() => new EventParser().push("x".repeat(2_000_001))).toThrow(
      /limit/,
    );
  });
  it("distinguishes terminal and active statuses", () => {
    for (const status of ["DONE", "ERROR", "CANCELLED", "BUDGET"])
      expect(terminal(status)).toBe(true);
    for (const status of [undefined, "QUEUED", "RUNNING"])
      expect(terminal(status)).toBe(false);
    // Metadata polling may lag the final execution snapshot (or vice versa).
    expect(terminal("RUNNING", "DONE")).toBe(true);
    expect(terminal("CANCELLED", "RUNNING")).toBe(true);
    expect(terminal("RUNNING", undefined)).toBe(false);
  });
});
