import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { attachment, chatInputDirectory } from "@/lib/files";
import { assertLocalRequest } from "@/lib/local-request";
import { mutateWorkspace } from "@/lib/store";
import { isChatRunning, startRun, workspaceSnapshot } from "@/lib/codex";
import { boardPrompt, boardSnapshot } from "@/lib/case-board";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ id: string }> };
const shared = globalThis as typeof globalThis & {
  boardRequests?: Set<string>;
};
const creating = (shared.boardRequests ||= new Set<string>());

export async function GET(request: Request, context: Context) {
  try {
    assertLocalRequest(request);
    const { id } = await context.params;
    const data = await workspaceSnapshot();
    const preview = boardSnapshot(data, id);
    const chat = data.chats.find((c) => c.caseId === id && c.board);
    return Response.json(
      {
        board: chat?.board || preview,
        chatId: chat?.id,
        message: chat?.messages.findLast((m) => m.role === "assistant"),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json({ error: "Case not found" }, { status: 404 });
  }
}

export async function POST(request: Request, context: Context) {
  let reserved: string | undefined;
  try {
    assertLocalRequest(request);
    const { id } = await context.params;
    if (creating.has(id))
      throw new Error("This case already has a board being generated.");
    creating.add(id);
    reserved = id;
    const chat = await mutateWorkspace((data) => {
      const board = boardSnapshot(data, id);
      if (!board.cards.length)
        throw new Error(
          "Add a case conversation or upload a case file before creating a knowledge graph.",
        );
      if (
        data.chats.some(
          (c) => c.caseId === id && c.board && isChatRunning(c.id),
        )
      )
        throw new Error("This case already has a board being generated.");
      const chat = {
        id: randomUUID(),
        caseId: id,
        title: "Knowledge graph",
        createdAt: board.createdAt,
        messages: [],
        board,
      };
      data.chats.unshift(chat);
      return chat;
    });
    const photos: { cardId: string; file: string }[] = [];
    const inputs = chatInputDirectory(chat.id);
    await mkdir(inputs, { recursive: true, mode: 0o700 });
    for (const card of chat.board.cards
      .filter((c) => c.kind === "image" && c.file)
      .slice(0, 3)) {
      try {
        const file = await attachment(card.chatId, card.file!);
        if (!file.image || file.size > 8 * 1024 * 1024) continue;
        await writeFile(
          path.join(inputs, file.name),
          await readFile(file.path),
          { flag: "wx", mode: 0o600 },
        );
        photos.push({ cardId: card.id, file: file.name });
      } catch {
        /* A missing original remains a source card without a generation reference. */
      }
    }
    const run = await startRun(
      chat.id,
      boardPrompt(chat.board, photos),
      "normal",
      photos.map((p) => p.file),
    );
    void run.completion.finally(() => creating.delete(id));
    await mutateWorkspace((data) => {
      const saved = data.chats.find((c) => c.id === chat.id);
      if (saved) saved.title = "Knowledge graph";
    });
    return Response.json(
      { board: chat.board, chatId: chat.id, message: run.message },
      { status: 201 },
    );
  } catch (error) {
    if (reserved) creating.delete(reserved);
    const message = (error as Error).message;
    return Response.json(
      { error: message },
      { status: message === "Case not found" ? 404 : 400 },
    );
  }
}
