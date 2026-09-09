import { assertLocalRequest, readJson } from "@/lib/local-request";
import { loadWorkspace } from "@/lib/store";
import { createMonitor, setMonitorEnabled } from "@/lib/monitors";
import {
  ensureMonitorScheduler,
  runMonitor,
  schedulerStatus,
} from "@/lib/monitor-scheduler";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    assertLocalRequest(request);
    await ensureMonitorScheduler();
    const caseId = new URL(request.url).searchParams.get("caseId");
    const data = await loadWorkspace();
    if (!caseId || !data.cases.some((c) => c.id === caseId))
      return Response.json({ error: "Case not found" }, { status: 404 });
    return Response.json(
      {
        monitors: (data.monitors || []).filter((m) => m.caseId === caseId),
        scheduler: schedulerStatus(),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}

export async function POST(request: Request) {
  try {
    assertLocalRequest(request);
    const body = await readJson(request);
    await ensureMonitorScheduler();
    if (typeof body.caseId !== "string")
      throw new Error("Select a case first.");
    if (body.action === "create") {
      for (const field of ["title", "prompt", "cron", "timezone"])
        if (typeof body[field] !== "string")
          throw new Error("Invalid schedule");
      return Response.json(
        await createMonitor({
          caseId: body.caseId,
          title: body.title as string,
          prompt: body.prompt as string,
          cron: body.cron as string,
          timezone: body.timezone as string,
        }),
        { status: 201 },
      );
    }
    if (typeof body.id !== "string") throw new Error("Select a monitor.");
    if (body.action === "toggle" && typeof body.enabled === "boolean")
      return Response.json(
        await setMonitorEnabled(body.id, body.caseId, body.enabled),
      );
    if (body.action === "run")
      return Response.json(await runMonitor(body.id, body.caseId, "manual"), {
        status: 202,
      });
    throw new Error("Invalid monitor action");
  } catch (error) {
    const message = (error as Error).message;
    return Response.json(
      { error: message },
      { status: /not found/i.test(message) ? 404 : 400 },
    );
  }
}
