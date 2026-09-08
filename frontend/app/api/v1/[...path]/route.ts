import type { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const base = new URL(
    process.env.DARKNETRA_API_BASE_URL ?? "http://127.0.0.1:8000",
  );
  const url = new URL(
    "/api/v1/" +
      path.map(encodeURIComponent).join("/") +
      request.nextUrl.search,
    base,
  );
  const headers = new Headers();
  for (const name of [
    "cookie",
    "authorization",
    "origin",
    "x-csrf-token",
    "content-type",
    "accept",
    "last-event-id",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const controller = new AbortController();
  const abort = () => controller.abort();
  request.signal.addEventListener("abort", abort, { once: true });
  try {
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      cache: "no-store",
      redirect: "manual",
      signal: controller.signal,
    };
    if (!["GET", "HEAD"].includes(request.method)) {
      init.body = request.body;
      init.duplex = "half";
    }
    const upstream = await fetch(url, init);
    const outgoing = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const name of [
      "content-type",
      "content-disposition",
      "retry-after",
      "x-request-id",
    ]) {
      const value = upstream.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie())
      outgoing.append("Set-Cookie", cookie);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: outgoing,
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "NETWORK_REQUIRED",
          message: "The backend is unavailable. Start the API and retry.",
        },
      },
      { status: 503 },
    );
  }
}
export {
  proxy as GET,
  proxy as POST,
  proxy as PATCH,
  proxy as DELETE,
  proxy as HEAD,
};
