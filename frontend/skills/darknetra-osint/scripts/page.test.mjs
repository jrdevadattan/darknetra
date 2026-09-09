import { expect, test } from "vitest";
import { parsePage } from "./osint.mjs";

const source = (body) => ({
  url: "https://example.com/SYNTHETIC",
  fetchedAt: "2026-09-09T00:00:00Z",
  mime: "text/html",
  body,
});
test("same-origin HTML base paths resolve real relative links and images correctly", () => {
  const result = parsePage(
    source(
      '<base href="/SYNTHETIC/docs/"><a href="next.html">SYNTHETIC next</a><img src="photo.png">',
    ),
  );
  expect(result.links[0].url).toBe(
    "https://example.com/SYNTHETIC/docs/next.html",
  );
  expect(result.images[0].url).toBe(
    "https://example.com/SYNTHETIC/docs/photo.png",
  );
});
test("all public body sections survive extraction, with separate paragraphs and source hash", () => {
  const page = parsePage(
    source(
      "<title>SYNTHETIC page</title><main><p>First section.</p></main><article><p>Second section.</p></article><aside><p>Public context.</p></aside><script>PRIVATE_SCRIPT</script>",
    ),
  );
  expect(page.text).toContain("Second section.");
  expect(page.text).toContain("Public context.");
  expect(page.text).not.toContain("PRIVATE_SCRIPT");
  expect(page.text).toContain("\n");
  expect(page.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(page.extraction.completeSite).toBe(false);
});
test("long pages have a resumable text section and line positions, not an unread tail", () => {
  const input = source(
    `<main><p>${"SYNTHETIC early text ".repeat(1100)}</p><p>SYNTHETIC final paragraph</p></main>`,
  );
  const first = parsePage(input);
  const next = parsePage(input, { offset: first.nextOffset });
  expect(first.nextOffset).toBe(16000);
  expect(next.text).toContain("SYNTHETIC final paragraph");
  expect(first.text + next.text).toHaveLength(first.textLength);
  expect(next.sha256).toBe(first.sha256);
  expect(next.textTruncated).toBe(false);
  expect(next.textOffset).toBe(16000);
});
test("wallet and access references have exact extracted-text locations without accusations", () => {
  const page = parsePage(
    source(
      '<p>SYNTHETIC Payment address: 0x1111111111111111111111111111111111111111</p><p>Sign in to see private records.</p><form><input type="password"></form>',
    ),
  );
  const wallet = page.findings.find((f) => f.kind === "wallet");
  expect(wallet).toMatchObject({
    sourceUrl: page.url,
    reviewStatus: "needs_review",
    location: { line: 1 },
  });
  expect(wallet.excerpt).toContain(
    "0x1111111111111111111111111111111111111111",
  );
  expect(page.access.passwordFieldPresent).toBe(true);
  expect(JSON.stringify(page.findings)).not.toMatch(
    /confirmed crime|illicit wallet/,
  );
});
test("a JavaScript shell is explicitly incomplete and authentication controls are never submitted", () => {
  const page = parsePage(
    source(
      '<div id="root"></div><script src="app.js"></script><noscript>Enable JavaScript</noscript>',
    ),
  );
  expect(page.extraction.javascriptLikely).toBe(true);
  expect(page.extraction.warnings.join(" ")).toMatch(/JavaScript/);
  expect(page.access.formsSubmitted).toBe(false);
});
