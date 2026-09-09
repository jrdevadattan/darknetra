import { readFile, realpath } from "node:fs/promises";
import path from "node:path";
import { boardImageDirectory } from "@/lib/board-image";
import { assertLocalRequest } from "@/lib/local-request";
import { loadWorkspace } from "@/lib/store";
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
    const data = await loadWorkspace();
    const chat = data.chats.find(
      (c) =>
        c.id === params.get("chat") &&
        c.caseId === id &&
        c.board?.caseId === id,
    );
    const image = chat?.messages.findLast(
      (m) => m.generatedImage,
    )?.generatedImage;
    if (
      !chat ||
      !image ||
      image.provider !== "imagegen" ||
      !/^([a-f0-9]{64})\.(?:png|jpg|webp)$/.test(image.file)
    )
      throw Error("Image not found");
    const root = await realpath(boardImageDirectory(chat.id)),
      file = await realpath(path.join(root, image.file));
    if (path.dirname(file) !== root) throw Error("Image not found");
    const ext = image.file.split(".").at(-1);
    return new Response(await readFile(file), {
      headers: {
        "Content-Type": ext === "jpg" ? "image/jpeg" : `image/${ext}`,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        ...(params.get("download") === "1"
          ? {
              "Content-Disposition": `attachment; filename="knowledge-graph.${ext}"`,
            }
          : {}),
      },
    });
  } catch {
    return Response.json({ error: "Image not found" }, { status: 404 });
  }
}
