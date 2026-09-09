import { test, expect, vi } from "vitest";
import {
  apifySearch,
  callApifyCatalog,
  mcpResponse,
} from "./apify-catalog.mjs";

test("catalog uses only anonymous MCP discovery calls and labels results as candidates", async () => {
  const request = vi.fn(async (_url, options) => {
    expect(options.headers.Authorization).toBeUndefined();
    expect(options.redirect).toBe("error");
    const body = JSON.parse(options.body);
    if (!body.id) return new Response(null, { status: 202 });
    const result =
      body.method === "initialize"
        ? { protocolVersion: "2025-03-26", capabilities: {} }
        : {
            structuredContent: {
              actors: [
                {
                  fullName: "SYNTHETIC/public-reader",
                  title: "SYNTHETIC reader",
                  description: "SYNTHETIC catalog fixture",
                },
              ],
            },
          };
    return new Response(
      `: keepalive\n\nevent: message\ndata: ${JSON.stringify({ jsonrpc: "2.0", id: body.id, result })}\n\n`,
      { headers: { "content-type": "text/event-stream" } },
    );
  });
  const result = await apifySearch("website content", 1, {
    call: (name, args) => callApifyCatalog(name, args, request),
  });
  expect(request).toHaveBeenCalledTimes(3);
  expect(JSON.parse(request.mock.calls[2][1].body).params).toEqual({
    name: "search-actors",
    arguments: { keywords: "website content", limit: 1 },
  });
  expect(result).toMatchObject({
    catalog: true,
    transport: "mcp",
    role: "backup",
  });
  expect(result.text).toContain("not connected tools or case evidence");
  await expect(
    callApifyCatalog("call-actor", {}, request),
  ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  expect(request).toHaveBeenCalledTimes(3);
});

test("MCP errors and malformed catalogs fail instead of reporting no results", async () => {
  expect(() =>
    mcpResponse(
      JSON.stringify({ jsonrpc: "2.0", id: 2, result: { isError: true } }),
      false,
      2,
    ),
  ).toThrow();
  await expect(
    apifySearch("weather", 1, { call: async () => ({ content: [] }) }),
  ).rejects.toMatchObject({ code: "UPSTREAM_UNAVAILABLE" });
  await expect(apifySearch("http://SYNTHETIC.onion/", 1)).rejects.toMatchObject(
    { code: "VALIDATION" },
  );
});
