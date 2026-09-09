import { expect, test } from "vitest";
import { gzipSync, brotliCompressSync } from "node:zlib";
import { responseBody } from "./response-body.mjs";
import { fetchSource } from "./osint.mjs";

test("SYNTHETIC compressed and declared-charset pages decode before extraction", () => {
  const text = "SYNTHETIC café";
  expect(
    responseBody(
      gzipSync(Buffer.from(text)),
      { "content-encoding": "gzip" },
      1000,
    ),
  ).toBe(text);
  expect(
    responseBody(
      brotliCompressSync(Buffer.from(text)),
      { "content-encoding": "br" },
      1000,
    ),
  ).toBe(text);
  expect(
    responseBody(
      Buffer.from(text, "latin1"),
      { "content-type": "text/html; charset=iso-8859-1" },
      1000,
    ),
  ).toBe(text);
});
test("decoded response limits remain enforced", () => {
  expect(() =>
    responseBody(
      gzipSync(Buffer.from("SYNTHETIC ".repeat(500))),
      { "content-encoding": "gzip" },
      100,
    ),
  ).toThrow(/read limit/);
  expect(() =>
    responseBody(
      Buffer.from("SYNTHETIC"),
      { "content-encoding": "unknown" },
      100,
    ),
  ).toThrow(/unsupported/);
});
test("site review transport rejects out-of-scope requests before network access", async () => {
  await expect(
    fetchSource("http://example.com/SYNTHETIC", 0, false, undefined, false, {
      requireHttps: true,
    }),
  ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  await expect(
    fetchSource("https://example.org/SYNTHETIC", 0, false, undefined, false, {
      allowedOrigin: "https://example.com",
    }),
  ).rejects.toMatchObject({ code: "POLICY_DENIED" });
  await expect(
    fetchSource("https://example.org/SYNTHETIC", 0, false, undefined, false, {
      allowedHostname: "example.com",
    }),
  ).rejects.toMatchObject({ code: "POLICY_DENIED" });
});
