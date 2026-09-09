import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import type { Case, Chat, WorkspaceData } from "./chat-types";

const shared = globalThis as typeof globalThis & {
  codexStoreQueue?: Promise<unknown>;
};
const file = () =>
  path.join(
    process.env.CODEX_CHAT_DATA_DIR || path.join(process.cwd(), ".codex-chat"),
    "workspace.json",
  );

async function readStore(): Promise<WorkspaceData> {
  try {
    const data = JSON.parse(await readFile(file(), "utf8"));
    if (
      data.version !== 1 ||
      !Array.isArray(data.cases) ||
      !Array.isArray(data.chats)
    )
      throw new Error("Unsupported workspace data");
    return data;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT")
      return { version: 1, cases: [], chats: [] };
    throw new Error(
      "Could not read the local workspace. Your saved file has not been changed.",
    );
  }
}

export async function loadWorkspace() {
  await shared.codexStoreQueue;
  return readStore();
}

export function mutateWorkspace<T>(
  change: (data: WorkspaceData) => T,
): Promise<T> {
  const operation = (shared.codexStoreQueue || Promise.resolve()).then(
    async () => {
      const data = await readStore();
      const result = change(data);
      const target = file();
      await mkdir(path.dirname(target), { recursive: true });
      const temporary = target + "." + randomUUID() + ".tmp";
      await writeFile(temporary, JSON.stringify(data), { mode: 0o600 });
      await rename(temporary, target);
      return structuredClone(result);
    },
  );
  shared.codexStoreQueue = operation.catch(() => undefined);
  return operation;
}

export function createCase(title: string, notes: string): Promise<Case> {
  return mutateWorkspace((data) => {
    if (!title.trim() || title.length > 300 || notes.length > 8000)
      throw new Error(
        "Enter a case title (up to 300 characters) and notes up to 8,000 characters.",
      );
    const item: Case = {
      id: randomUUID(),
      title: title.trim(),
      notes: notes.trim(),
      createdAt: new Date().toISOString(),
    };
    data.cases.unshift(item);
    return item;
  });
}

export function createChat(caseId: string | null = null): Promise<Chat> {
  return mutateWorkspace((data) => {
    if (caseId && !data.cases.some((item) => item.id === caseId))
      throw new Error("Case not found");
    const chat: Chat = {
      id: randomUUID(),
      caseId,
      title: "New chat",
      createdAt: new Date().toISOString(),
      messages: [],
    };
    data.chats.unshift(chat);
    return chat;
  });
}

export class ChatNotFoundError extends Error {
  constructor() {
    super("Chat not found");
  }
}

export function setChatArchived(id: string, archived: boolean): Promise<Chat> {
  return mutateWorkspace((data) => {
    const chat = data.chats.find((item) => item.id === id);
    if (!chat) throw new ChatNotFoundError();
    if (archived) chat.archivedAt ||= new Date().toISOString();
    else delete chat.archivedAt;
    return chat;
  });
}
