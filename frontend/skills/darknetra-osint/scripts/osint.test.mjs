import { expect, test } from "vitest";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  isPublicAddress,
  publicUrl,
  parseIndex,
  parseFeed,
  parsePage,
  iconData,
  faviconFor,
  imageMetadata,
} from "./osint.mjs";

test("page image inventory is bounded, deduplicated and never claims retrieval", () => {
  const data = parsePage({
    url: "https://example.com/SYNTHETIC/page",
    mime: "text/html",
    body: `<img src="/SYNTHETIC.png" alt="SYNTHETIC photo"><img src="/SYNTHETIC.png"><img data-src="https://example.org/SYNTHETIC.jpg"><img src="http://127.0.0.1/private"><img src="data:image/png;base64,AAAA">${Array.from({ length: 45 }, (_, i) => `<img src="/SYNTHETIC-${i}.png">`).join("")}`,
  });
  expect(data.images).toHaveLength(40);
  expect(data.images[0]).toMatchObject({
    url: "https://example.com/SYNTHETIC.png",
    title: "SYNTHETIC photo",
    targetFetched: false,
  });
  expect(data.imageSummary).toMatchObject({
    unique: 47,
    returned: 40,
    truncated: true,
  });
  expect(JSON.stringify(data.images)).not.toContain("127.0.0.1");
});

test("remote image metadata reads original bytes and records hash and source time", async () => {
  const bytes = Buffer.from("89504e470d0a1a0a", "hex");
  const calls = [];
  const result = await imageMetadata(
    "https://example.com/SYNTHETIC.png",
    async (...args) => {
      calls.push(args);
      return {
        body: bytes,
        url: args[0],
        fetchedAt: "2026-09-08T10:00:00Z",
        mime: "image/png",
      };
    },
    async (input) => {
      expect(input).toEqual(bytes);
      return { analysis: "metadata", text: "SYNTHETIC metadata" };
    },
  );
  expect(result).toMatchObject({
    url: "https://example.com/SYNTHETIC.png",
    fetchedAt: "2026-09-08T10:00:00Z",
    size: 8,
    sha256: expect.stringMatching(/^[a-f0-9]{64}$/),
  });
  expect(calls[0][4]).toBe(true);
  await expect(
    imageMetadata("http://127.0.0.1/private", async () => {
      throw Error("must not fetch");
    }),
  ).rejects.toThrow();
  await expect(
    imageMetadata("https://example.com/SYNTHETIC.png", async () => ({
      body: Buffer.from("<html>SYNTHETIC</html>"),
      mime: "image/png",
    })),
  ).rejects.toMatchObject({ code: "UNSUPPORTED_TYPE" });
});

const syntheticIcon = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=",
  "base64",
);

test("favicon assets allow bounded raster images and reject executable or oversized content", () => {
  expect(iconData(syntheticIcon)).toMatch(/^data:image\/png;base64,/);
  expect(
    iconData(Buffer.from('<svg onload="SYNTHETIC()"></svg>')),
  ).toBeUndefined();
  expect(
    iconData(Buffer.from("<html>SYNTHETIC error page</html>")),
  ).toBeUndefined();
  expect(
    iconData(Buffer.concat([syntheticIcon, Buffer.alloc(32768)])),
  ).toBeUndefined();
});

test("favicon reads stay on the retrieved origin, try one declared icon then the root fallback", async () => {
  const calls = [];
  const source = {
    url: "https://example.com/SYNTHETIC/page",
    body: '<link rel="icon" href="http://127.0.0.1/private"><link rel="icon" href="https://example.org/tracker"><link rel="icon" href="/icon.svg"><link rel="shortcut icon" href="/assets/SYNTHETIC.png"><link rel="icon" href="/extra.png">',
  };
  const icon = await faviconFor(source, async (...args) => {
    calls.push(args);
    if (calls.length === 1) throw new Error("SYNTHETIC missing asset");
    return { body: syntheticIcon };
  });
  expect(icon).toBe(iconData(syntheticIcon));
  expect(calls).toEqual([
    [
      "https://example.com/assets/SYNTHETIC.png",
      0,
      false,
      "https://example.com",
    ],
    ["https://example.com/favicon.ico", 0, false, "https://example.com"],
  ]);
});

test("missing favicons do not fail a page read and onion assets retain the Tor transport", async () => {
  const origin = `http://${"a".repeat(56)}.onion`;
  const calls = [];
  const icon = await faviconFor(
    { url: `${origin}/SYNTHETIC`, body: "<title>SYNTHETIC</title>" },
    async (...args) => {
      calls.push(args);
      throw new Error("SYNTHETIC timeout");
    },
  );
  expect(icon).toBeUndefined();
  expect(calls).toEqual([[`${origin}/favicon.ico`, 0, true, origin]]);
});

test("public source reads reject private networks, non-web schemes and credentials", () => {
  for (const url of [
    "http://127.0.0.1",
    "http://2130706433",
    "http://169.254.169.254",
    "http://10.0.0.1",
    "http://[::1]",
    "http://[::ffff:127.0.0.1]",
    "file:///etc/passwd",
    "https://user:secret@example.com",
    "http://example.com:8000",
  ])
    expect(() => publicUrl(url)).toThrow();
  for (const ip of [
    "192.168.1.1",
    "10.0.0.1",
    "172.16.0.1",
    "127.0.0.1",
    "169.254.169.254",
    "::1",
    "fc00::1",
    "fe80::1",
    "::ffff:127.0.0.1",
  ])
    expect(isPublicAddress(ip)).toBe(false);
  expect(isPublicAddress("93.184.215.14")).toBe(true);
  expect(publicUrl("https://example.com/#fragment").href).toBe(
    "https://example.com/",
  );
});

test("Robin parses bounded index entries, deduplicates and excludes ads without fetching targets", () => {
  const onion = `http://${"a".repeat(56)}.onion/`;
  const entry = (title, url = onion) =>
    `<div class="result-block"><div class="title"><a data-category="text-result">${title}</a></div><div class="link">${url}</div></div>`;
  const html = `<div class="search-results">${entry("SYNTHETIC first")}${entry("SYNTHETIC duplicate")}${entry("SYNTHETIC invalid", "http://127.0.0.1")}${entry("SYNTHETIC ad").replace("result-block", 'result-block"><span class="label-ad"></span><div class="ignored')}</div>`;
  expect(parseIndex(html, "onionland")).toEqual([
    { title: "SYNTHETIC first", url: onion, targetFetched: false },
  ]);
  expect(() =>
    parseIndex("<html>Provider landing page</html>", "ahmia"),
  ).toThrow("recognizable");
  expect(
    parseIndex(
      '<div id="ahmiaResultsPage"><div id="noResults"></div></div>',
      "ahmia",
    ),
  ).toEqual([]);
  expect(() =>
    parseIndex('<form id="challenge-form"></form>', "onionland"),
  ).toThrow("challenge");
});

test("source parsers strip executable page elements and support RSS and Atom", () => {
  const source = {
    url: "https://example.com/",
    fetchedAt: "SYNTHETIC",
    mime: "text/html",
    body: "<title>SYNTHETIC page</title><main>Visible text<script>privateScript()</script></main>",
  };
  expect(parsePage(source)).toMatchObject({
    title: "SYNTHETIC page",
    text: "Visible text",
  });
  const atom = parseFeed({
    ...source,
    body: '<feed><entry><title>SYNTHETIC entry</title><link href="/news"/><summary>News text</summary></entry></feed>',
  });
  expect(atom.entries[0]).toMatchObject({
    title: "SYNTHETIC entry",
    url: "https://example.com/news",
  });
  expect(() =>
    parseFeed({ ...source, body: "<html>challenge</html>" }),
  ).toThrow("RSS or Atom");
});

test("the executable returns structured failures with nonzero exit status", () => {
  try {
    execFileSync(
      process.execPath,
      [
        fileURLToPath(new URL("./osint.mjs", import.meta.url)),
        "page",
        "http://127.0.0.1",
      ],
      { encoding: "utf8" },
    );
    throw new Error("Expected the command to fail");
  } catch (error) {
    expect(error.status).toBe(1);
    expect(JSON.parse(error.stdout)).toMatchObject({
      ok: false,
      error: { code: "POLICY_DENIED" },
    });
  }
});

test("page links are real deduplicated public anchors resolved against the retrieved page", () => {
  const result = parsePage({
    url: "https://example.com/case/start",
    fetchedAt: "SYNTHETIC",
    mime: "text/html",
    body: `<title>SYNTHETIC inventory</title><base href="https://other.example/">
      <main><a href="https://external.example/report">External report</a>
      <a href="../record#top">SYNTHETIC record</a><a href="/record#bottom">Duplicate</a>
      <a href="?page=2">Next page</a><a href="#local">Local anchor</a>
      <a href="http://127.0.0.1/secret">Private</a><a href="javascript:alert(1)">Script</a>
      <a href="mailto:nobody@example.com">Email</a><a href="https://user:pass@example.com">Credentials</a>
      <form><a href="/submit">Action</a></form></main>`,
  });
  expect(result.links).toEqual([
    {
      url: "https://example.com/record",
      title: "SYNTHETIC record",
      sameSite: true,
      targetFetched: false,
    },
    {
      url: "https://example.com/case/start?page=2",
      title: "Next page",
      sameSite: true,
      targetFetched: false,
    },
    {
      url: "https://external.example/report",
      title: "External report",
      sameSite: false,
      targetFetched: false,
    },
  ]);
  expect(result.linkSummary).toMatchObject({
    unique: 3,
    sameSite: 2,
    external: 1,
    returned: 3,
    truncated: false,
  });
});

test("oversized page inventories and text are explicitly incomplete", () => {
  const result = parsePage({
    url: "https://example.com/",
    fetchedAt: "SYNTHETIC",
    mime: "text/html",
    body:
      `<main>${"SYNTHETIC ".repeat(1700)}</main>` +
      Array.from(
        { length: 105 },
        (_, n) => `<a href="/page-${n}">SYNTHETIC ${n}</a>`,
      ).join(""),
  });
  expect(result.text).toHaveLength(16000);
  expect(result.textTruncated).toBe(true);
  expect(result.links).toHaveLength(100);
  expect(result.linkSummary).toMatchObject({
    unique: 105,
    returned: 100,
    truncated: true,
  });
});
