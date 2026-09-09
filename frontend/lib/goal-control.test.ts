import { afterEach, expect, test, vi } from "vitest";
import { EventEmitter } from "node:events";
import { PassThrough, Writable } from "node:stream";
import { tmpdir } from "node:os";
import path from "node:path";
const mock = vi.hoisted(() => ({ spawn: vi.fn() }));
vi.mock("node:child_process", () => ({ spawn: mock.spawn }));
import { clearNativeGoal } from "./goal-control";
afterEach(() => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

function processFixture(deny = false) {
  const requests: { id?: number; method: string; params: unknown }[] = [];
  const stdout = new PassThrough();
  const child = Object.assign(new EventEmitter(), {
    stdout,
    stderr: new PassThrough(),
    kill: vi.fn(),
    stdin: new Writable({
      write(chunk, _encoding, callback) {
        const request = JSON.parse(chunk.toString());
        requests.push(request);
        if (request.id)
          queueMicrotask(() =>
            stdout.write(
              JSON.stringify({
                id: request.id,
                ...(request.id === 2 && deny
                  ? { error: { message: "SYNTHETIC denial" } }
                  : { result: request.id === 1 ? {} : { cleared: true } }),
              }) + "\n",
            ),
          );
        callback();
      },
    }),
  });
  mock.spawn.mockReturnValue(child);
  vi.stubEnv("CODEX_HOME", path.join(tmpdir(), "SYNTHETIC-private-cli"));
  return { child, requests };
}

test("a new request clears only its exact native goal through the CLI metadata protocol", async () => {
  const { child, requests } = processFixture();
  const id = "00000000-0000-4000-8000-000000000001";
  await clearNativeGoal(id);
  expect(requests.map((request) => request.method)).toEqual([
    "initialize",
    "initialized",
    "thread/goal/clear",
  ]);
  expect(requests.at(-1)?.params).toEqual({ threadId: id });
  expect(mock.spawn.mock.calls[0][1]).toContain("--stdio");
  expect(child.kill).toHaveBeenCalled();
});

test("a goal-control denial or invalid session cannot silently launch a replacement objective", async () => {
  processFixture(true);
  await expect(clearNativeGoal("not-a-session")).rejects.toThrow(
    "Invalid investigation session",
  );
  expect(mock.spawn).not.toHaveBeenCalled();
  await expect(
    clearNativeGoal("00000000-0000-4000-8000-000000000001"),
  ).rejects.toThrow("could not reset");
});
