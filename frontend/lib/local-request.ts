export function assertLocalRequest(request: Request) {
  const url = new URL(request.url);
  const host = request.headers.get("host") || url.host;
  if (
    !["localhost", "127.0.0.1", "[::1]"].includes(
      new URL(`http://${host}`).hostname,
    )
  )
    throw new Error("This workspace is local to this computer.");
  const origin = request.headers.get("origin");
  if (request.method !== "GET" && origin !== `${url.protocol}//${host}`)
    throw new Error("Request origin does not match this workspace.");
  if (request.headers.get("sec-fetch-site") === "cross-site")
    throw new Error("Cross-site requests are not allowed.");
}

export async function readJson(
  request: Request,
): Promise<Record<string, unknown>> {
  if (!request.headers.get("content-type")?.startsWith("application/json"))
    throw new Error("Expected JSON");
  const reader = request.body?.getReader();
  if (!reader) throw new Error("Request body is required");
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > 64 * 1024) {
      await reader.cancel();
      throw new Error("Request is too large");
    }
    chunks.push(value);
  }
  const value = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Expected a JSON object");
  return value;
}
