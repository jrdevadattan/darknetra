import { brotliDecompressSync, gunzipSync, inflateSync } from "node:zlib";

export function responseBody(bytes, headers, limit, binary = false) {
  const fail = (code, message) => Object.assign(new Error(message), { code });
  const encoding = String(headers["content-encoding"] || "identity")
    .toLowerCase()
    .trim();
  const decoders = {
    gzip: gunzipSync,
    deflate: inflateSync,
    br: brotliDecompressSync,
  };
  if (encoding !== "identity") {
    if (!decoders[encoding])
      throw fail(
        "UNSUPPORTED_TYPE",
        "The source uses an unsupported response encoding.",
      );
    try {
      bytes = decoders[encoding](bytes, { maxOutputLength: limit });
    } catch {
      throw fail(
        "SIZE_LIMIT",
        "The compressed response is invalid or exceeds the decoded read limit.",
      );
    }
  }
  if (bytes.length > limit)
    throw fail("SIZE_LIMIT", "The decoded source exceeds the read limit.");
  if (binary) return bytes;
  const charset =
    String(headers["content-type"] || "").match(
      /charset\s*=\s*["']?([^\s;"']+)/i,
    )?.[1] || "utf-8";
  try {
    return new TextDecoder(charset).decode(bytes);
  } catch {
    throw fail(
      "UNSUPPORTED_TYPE",
      "The source uses an unsupported text character encoding.",
    );
  }
}
