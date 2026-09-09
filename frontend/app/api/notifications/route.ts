import { assertLocalRequest, readJson } from "@/lib/local-request";
import { loadWorkspace, mutateWorkspace } from "@/lib/store";
import {
  deliverPush,
  pushPublicKey,
  removeSubscription,
  saveSubscription,
  subscriptionStatus,
} from "@/lib/push";
import { randomUUID } from "node:crypto";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  try {
    assertLocalRequest(request);
    const data = await loadWorkspace();
    return Response.json(
      {
        notifications: data.notifications || [],
        publicKey: await pushPublicKey(),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return Response.json(
      { error: "Notifications could not be loaded." },
      { status: 400 },
    );
  }
}
export async function POST(request: Request) {
  try {
    assertLocalRequest(request);
    const body = await readJson(request);
    if (body.action === "subscribe") {
      await saveSubscription(body.subscription, body.failuresOnly === true);
      return Response.json({ ok: true });
    }
    if (["unsubscribe", "status", "test"].includes(String(body.action))) {
      if (typeof body.endpoint !== "string" || body.endpoint.length > 4096)
        throw new Error("Invalid subscription.");
      if (body.action === "unsubscribe") {
        await removeSubscription(body.endpoint);
        return Response.json({ ok: true });
      }
      if (body.action === "status")
        return Response.json(await subscriptionStatus(body.endpoint));
      const status = await subscriptionStatus(body.endpoint);
      if (!status.enabled)
        throw new Error("Enable notifications on this browser first.");
      const result = await deliverPush(
        {
          id: randomUUID(),
          at: new Date().toISOString(),
          kind: "complete",
          title: "DARKNETRA notifications",
          body: "Notifications are ready for this browser.",
          caseId: "",
          chatId: "",
        },
        body.endpoint,
      );
      if (!result.sent)
        throw new Error(
          "The push service could not accept this notification. Check connectivity or enable notifications again.",
        );
      return Response.json({ ok: true });
    }
    if (body.action === "read") {
      if (typeof body.id !== "string" && body.id !== undefined)
        throw new Error("Invalid notification.");
      await mutateWorkspace((data) => {
        for (const n of data.notifications || [])
          if (!body.id || n.id === body.id) n.read = true;
      });
      return Response.json({ ok: true });
    }
    throw new Error("Invalid notification action.");
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}
