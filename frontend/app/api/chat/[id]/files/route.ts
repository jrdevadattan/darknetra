import { readFile } from "node:fs/promises";
import { attachment, requireChat, saveUpload } from "@/lib/files";
import { assertLocalRequest } from "@/lib/local-request";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ id: string }> };

export async function POST(request: Request, context: Context) {
  try {
    assertLocalRequest(request);
    return Response.json(await saveUpload((await context.params).id, request));
  } catch (error) {
    const message = (error as Error).message;
    return Response.json(
      { error: message },
      { status: message === "Chat not found" ? 404 : 400 },
    );
  }
}

export async function GET(request: Request, context: Context) {
  try {
    assertLocalRequest(request);
    const { id } = await context.params;
    await requireChat(id);
    const file = await attachment(
      id,
      new URL(request.url).searchParams.get("name") || "",
    );
    return new Response(await readFile(file.path), {
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": `attachment; filename="${file.label}"`,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return Response.json({ error: "File not found" }, { status: 404 });
  }
}
