import { assertLocalRequest } from "@/lib/local-request";
import { providerIntegrations } from "@/lib/provider-integrations";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    assertLocalRequest(request);
    return Response.json(await providerIntegrations(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      { error: "Could not read intelligence tool configuration." },
      { status: 400 },
    );
  }
}
