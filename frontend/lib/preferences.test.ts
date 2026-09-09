import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { GET, POST } from "../app/api/preferences/route";
import { createCase, createChat, loadWorkspace } from "./store";

let directory: string;
beforeEach(async () => {
  directory = await mkdtemp(path.join(tmpdir(), "SYNTHETIC-language-"));
  vi.stubEnv("CODEX_CHAT_DATA_DIR", directory);
});
afterEach(async () => {
  vi.unstubAllEnvs();
  await rm(directory, { recursive: true, force: true });
});
const request = (language: unknown, origin = "http://localhost:3000") =>
  new Request("http://localhost:3000/api/preferences", {
    method: "POST",
    headers: { origin, "Content-Type": "application/json" },
    body: JSON.stringify({ language }),
  });

test("language survives disk reload without changing saved cases or chats", async () => {
  const caseItem = await createCase(
    "SYNTHETIC language case",
    "SYNTHETIC unchanged notes",
  );
  const chat = await createChat(caseItem.id);
  expect(
    await (
      await GET(new Request("http://localhost:3000/api/preferences"))
    ).json(),
  ).toEqual({ language: "en" });
  expect((await POST(request("pa"))).status).toBe(200);
  expect((await loadWorkspace()).preferences?.language).toBe("pa");
  expect(
    await (
      await GET(new Request("http://localhost:3000/api/preferences"))
    ).json(),
  ).toEqual({ language: "pa" });
  expect((await loadWorkspace()).cases).toEqual([caseItem]);
  expect((await loadWorkspace()).chats).toEqual([chat]);
});

test("unsupported codes and cross-origin writes cannot change preferences", async () => {
  await POST(request("hi"));
  expect((await POST(request("SYNTHETIC invalid"))).status).toBe(400);
  expect((await POST(request("ur", "https://example.com"))).status).toBe(400);
  expect((await loadWorkspace()).preferences?.language).toBe("hi");
});
