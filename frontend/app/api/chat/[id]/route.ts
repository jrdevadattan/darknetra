import { cancelRun, runStream, startRun } from "@/lib/codex";
import { assertLocalRequest, readJson } from "@/lib/local-request";
import { ensureMonitorScheduler } from "@/lib/monitor-scheduler";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ id: string }> };

export async function POST(request: Request, context: Context) {
  try {
    assertLocalRequest(request);
    const body = await readJson(request);
    if (
      typeof body.text !== "string" ||
      ![undefined, "normal", "thinking", "netra"].includes(
        body.mode as string,
      ) ||
      (body.attachments !== undefined &&
        (!Array.isArray(body.attachments) ||
          body.attachments.length > 8 ||
          body.attachments.some((name) => typeof name !== "string")))
    )
      throw new Error("Invalid chat message");
    const { id } = await context.params;
    await ensureMonitorScheduler();
    const run = await startRun(
      id,
      body.text,
      body.mode === "netra"
        ? "netra"
        : body.mode === "thinking"
          ? "thinking"
          : "normal",
      body.attachments as string[] | undefined,
      {
        monitorFromChat: true,
        timezone:
          typeof body.timezone === "string" && body.timezone.length < 100
            ? body.timezone
            : "UTC",
      },
    );
    return new Response(runStream(run), {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}
export async function DELETE(request: Request, context: Context) {
  try {
    assertLocalRequest(request);
    cancelRun((await context.params).id);
    return Response.json({ ok: true });
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}
