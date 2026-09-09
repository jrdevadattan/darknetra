import { readFile } from "node:fs/promises";
import { assertLocalRequest } from "@/lib/local-request";
import { loadWorkspace } from "@/lib/store";
import { attachment } from "@/lib/files";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    assertLocalRequest(request);
    const { id } = await context.params;
    const params = new URL(request.url).searchParams;
    const chatId = params.get("chat") || "",
      name = params.get("name") || "";
    const data = await loadWorkspace();
    const chat = data.chats.find((c) => c.id === chatId && c.caseId === id);
    if (
      !data.cases.some((c) => c.id === id) ||
      !chat?.messages.some((m) => m.attachments?.some((f) => f.name === name))
    )
      throw new Error("File not found");
    const file = await attachment(chatId, name);
    if (!file.image || file.size > 8 * 1024 * 1024)
      throw new Error("Preview unavailable");
    const bytes = await readFile(file.path);
    const type =
      bytes[0] === 137
        ? "image/png"
        : bytes[0] === 255
          ? "image/jpeg"
          : "image/webp";
    return new Response(bytes, {
      headers: {
        "Content-Type": type,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return Response.json({ error: "File not found" }, { status: 404 });
  }
}
