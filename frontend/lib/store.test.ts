import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { runStream, startRun } from "./codex";
import {
  createCase,
  createChat,
  loadWorkspace,
  mutateWorkspace,
  setChatArchived,
} from "./store";
import { POST } from "../app/api/workspace/route";

let directory: string;
beforeEach(async () => {
  directory = await mkdtemp(path.join(tmpdir(), "synthetic-cli-store-"));
  vi.stubEnv("CODEX_CHAT_DATA_DIR", directory);
});
afterEach(async () => {
  vi.unstubAllEnvs();
  await rm(directory, { recursive: true, force: true });
});

test("concurrent case writes and conversations survive a disk reload", async () => {
  const cases = await Promise.all(
    Array.from({ length: 8 }, (_, i) =>
      createCase(`SYNTHETIC ${i}`, "SYNTHETIC scope"),
    ),
  );
  const first = await createChat(cases[0].id);
  const second = await createChat(cases[1].id);
  await mutateWorkspace((state) => {
    state.chats
      .find((chat) => chat.id === first.id)!
      .messages.push({
        id: "synthetic-message",
        role: "user",
        text: "SYNTHETIC first case only",
        at: new Date().toISOString(),
        status: "done",
        activity: [],
      });
  });
  const state = await loadWorkspace();
  expect(state.cases).toHaveLength(8);
  expect(
    state.chats.find((chat) => chat.id === first.id)?.messages[0].text,
  ).toBe("SYNTHETIC first case only");
  expect(state.chats.find((chat) => chat.id === second.id)?.messages).toEqual(
    [],
  );
});

test("rejects unknown cases and invalid titles without writing a conversation", async () => {
  await expect(createCase("  ", "")).rejects.toThrow();
  await expect(createChat("../../outside")).rejects.toThrow();
  expect((await loadWorkspace()).chats).toEqual([]);
});

test("does not overwrite a damaged store with an empty workspace", async () => {
  await writeFile(
    path.join(directory, "workspace.json"),
    "SYNTHETIC damaged JSON",
  );
  await expect(createCase("SYNTHETIC new", "")).rejects.toThrow();
  expect(await readFile(path.join(directory, "workspace.json"), "utf8")).toBe(
    "SYNTHETIC damaged JSON",
  );
});

test("archiving and restoring preserve conversations, files, sessions and monitoring", async () => {
  const caseItem = await createCase("SYNTHETIC archive case", "");
  const chat = await createChat(caseItem.id);
  await createChat();
  await mutateWorkspace((data) => {
    const saved = data.chats.find((item) => item.id === chat.id)!;
    saved.sessionId = "SYNTHETIC-session";
    saved.messages.push({
      id: "SYNTHETIC-message",
      role: "user",
      text: "SYNTHETIC saved material",
      at: saved.createdAt,
      status: "done",
      activity: [],
      attachments: [
        { name: "synthetic.txt", label: "SYNTHETIC file", size: 20 },
      ],
    });
    data.monitors = [
      {
        id: "SYNTHETIC-monitor",
        chatId: chat.id,
        caseId: caseItem.id,
        title: "SYNTHETIC monitor",
        prompt: "SYNTHETIC check",
        cron: "0 9 * * *",
        timezone: "UTC",
        enabled: true,
        createdAt: saved.createdAt,
        nextRunAt: "2099-01-01T09:00:00.000Z",
        runs: [],
      },
    ];
  });
  const before = await loadWorkspace();
  const archived = await setChatArchived(chat.id, true);
  expect(archived.archivedAt).toBeTruthy();
  expect((await setChatArchived(chat.id, true)).archivedAt).toBe(
    archived.archivedAt,
  );
  expect((await loadWorkspace()).monitors).toEqual(before.monitors);
  await expect(
    startRun(chat.id, "SYNTHETIC manual message", "normal", [], {
      monitorFromChat: true,
      timezone: "UTC",
    }),
  ).rejects.toThrow("Restore this archived chat");
  await setChatArchived(chat.id, false);
  expect(await loadWorkspace()).toEqual(before);
});

test("archive API validates actions and origin without changing other chats", async () => {
  const chat = await createChat();
  const post = (body: unknown, origin = "http://localhost:3000") =>
    POST(
      new Request("http://localhost:3000/api/workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json", Origin: origin },
        body: JSON.stringify(body),
      }),
    );
  expect(
    (
      await post({
        type: "archive-chat",
        chatId: "SYNTHETIC-missing",
        archived: true,
      })
    ).status,
  ).toBe(404);
  expect(
    (await post({ type: "archive-chat", chatId: chat.id, archived: "false" }))
      .status,
  ).toBe(400);
  expect(
    (
      await post(
        { type: "archive-chat", chatId: chat.id, archived: true },
        "https://synthetic.invalid",
      )
    ).status,
  ).toBe(400);
  expect((await loadWorkspace()).chats).toEqual([chat]);
  expect(
    (await post({ type: "archive-chat", chatId: chat.id, archived: true }))
      .status,
  ).toBe(200);
  expect((await loadWorkspace()).chats[0].archivedAt).toBeTruthy();
  expect(
    (await post({ type: "archive-chat", chatId: chat.id, archived: false }))
      .status,
  ).toBe(200);
  expect((await loadWorkspace()).chats).toEqual([chat]);
});

test("a missing CLI produces a saved error and releases the active chat", async () => {
  vi.stubEnv("CODEX_BIN", path.join(directory, "SYNTHETIC-missing-codex.exe"));
  const chat = await createChat();
  const run = await startRun(chat.id, "SYNTHETIC hello", "normal");
  const stream = runStream(run).getReader();
  while (!(await stream.read()).done) {
    /* Wait for the spawn error and persisted result. */
  }
  const saved = (await loadWorkspace()).chats[0].messages.at(-1)!;
  expect(saved.status).toBe("error");
  expect(saved.error).toContain("local assistant runtime was not found");
  const retry = await startRun(chat.id, "SYNTHETIC retry", "normal");
  const second = runStream(retry).getReader();
  while (!(await second.read()).done) {
    /* The previous run must release the chat lock. */
  }
  expect((await loadWorkspace()).chats[0].messages).toHaveLength(4);
});
