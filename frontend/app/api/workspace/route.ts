import {
  ChatNotFoundError,
  createCase,
  createChat,
  setChatArchived,
} from "@/lib/store";
import { workspaceSnapshot } from "@/lib/codex";
import { assertLocalRequest, readJson } from "@/lib/local-request";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    assertLocalRequest(request);
    return Response.json(await workspaceSnapshot(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}
export async function POST(request: Request) {
  try {
    assertLocalRequest(request);
    const body = await readJson(request);
    if (
      body.type === "archive-chat" &&
      typeof body.chatId === "string" &&
      typeof body.archived === "boolean"
    )
      return Response.json(await setChatArchived(body.chatId, body.archived));
    if (
      body.type === "case" &&
      typeof body.title === "string" &&
      (body.notes === undefined || typeof body.notes === "string")
    )
      return Response.json(
        await createCase(body.title, (body.notes as string) || ""),
        { status: 201 },
      );
    if (
      body.type === "chat" &&
      (body.caseId == null || typeof body.caseId === "string")
    )
      return Response.json(await createChat(body.caseId as string | null), {
        status: 201,
      });
    throw new Error("Invalid workspace action");
  } catch (error) {
    return Response.json(
      { error: (error as Error).message },
      {
        status: error instanceof ChatNotFoundError ? 404 : 400,
      },
    );
  }
}
