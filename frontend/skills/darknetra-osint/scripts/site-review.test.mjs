import { expect, test } from "vitest";
import { siteReview } from "./site-review.mjs";

const root = "https://example.com/SYNTHETIC/";
const page = (url, body) => ({
  url,
  body,
  mime: "text/html",
  fetchedAt: "2026-09-09T00:00:00Z",
});
test("a canonical page already queued is retained when an earlier alias retrieves it", async () => {
  const calls = [];
  const result = await siteReview(root, 2, {
    pause: async () => {},
    reader: async (url) => {
      calls.push(url);
      return url === root
        ? page(
            url,
            '<a href="alias">Alias</a><a href="canonical">Canonical</a>',
          )
        : page(root + "canonical", "SYNTHETIC canonical content");
    },
  });
  expect(calls).toEqual([root, root + "alias"]);
  expect(result.coverage).toMatchObject({ retrieved: 2, pending: 0 });
  expect(result.pages[1]).toMatchObject({
    url: root + "canonical",
    requestedUrl: root + "alias",
    textOffset: 0,
    text: "SYNTHETIC canonical content",
  });
});
test("an access denial or rate limit stops further same-site requests", async () => {
  const calls = [];
  const result = await siteReview(root, 10, {
    pause: async () => {},
    reader: async (url) => {
      calls.push(url);
      if (url === root)
        return page(url, '<a href="one">One</a><a href="two">Two</a>');
      throw Object.assign(Error("SYNTHETIC rate limited"), {
        code: "RATE_LIMITED",
      });
    },
  });
  expect(calls).toHaveLength(2);
  expect(result.coverage).toMatchObject({
    stopReason: "rate_limited",
    pending: 1,
  });
});
test("scoped public links are followed breadth first, with source parents and distinct failed/access/external outcomes", async () => {
  const calls = [];
  const data = await siteReview(root, 10, {
    reader: async (url, ...args) => {
      calls.push({ url, constraints: args.at(-1) });
      if (url.endsWith("/missing"))
        throw Object.assign(Error("SYNTHETIC HTTP 404"), {
          code: "UPSTREAM_UNAVAILABLE",
        });
      if (url === root)
        return page(
          url,
          '<p>SYNTHETIC start</p><a href="about">About</a><a href="missing">Missing</a><a href="login">Login</a><a href="https://example.org/reference">External</a>',
        );
      if (url.endsWith("/about"))
        return page(
          url,
          '<p>SYNTHETIC about</p><a href="details">More</a><a href="./">Duplicate</a>',
        );
      return page(url, "<p>SYNTHETIC details</p>");
    },
    pause: async () => {},
  });
  expect(calls.map((c) => c.url)).toEqual([
    root,
    root + "about",
    root + "missing",
    root + "details",
  ]);
  expect(data.pages.find((p) => p.url.endsWith("/details"))).toMatchObject({
    parentUrl: root + "about",
    depth: 2,
    status: "retrieved",
  });
  expect(data.pages.find((p) => p.url.endsWith("/login"))).toMatchObject({
    status: "skipped",
  });
  expect(data.pages.find((p) => p.url.endsWith("/missing"))).toMatchObject({
    status: "failed",
  });
  expect(data.coverage).toMatchObject({
    attempted: 4,
    retrieved: 3,
    failed: 1,
    skipped: 2,
    complete: false,
  });
  expect(calls[1].constraints.allowedOrigin).toBe(new URL(root).origin);
});
test("page limits leave a concrete frontier and long text can be read in further sections", async () => {
  const data = await siteReview(root, 1, {
    reader: async (url) =>
      page(url, `<p>${"SYNTHETIC ".repeat(900)}</p><a href="next">Next</a>`),
    pause: async () => {},
  });
  expect(data.coverage.stopReason).toBe("page_limit");
  expect(data.coverage.pending).toBe(1);
  expect(data.pages[0]).toMatchObject({
    textTruncated: true,
    nextOffset: 6000,
  });
  expect(data.pages[1]).toMatchObject({
    url: root + "next",
    status: "pending",
  });
});
test("a redirect outside scope never becomes a retrieved case page", async () => {
  const data = await siteReview(root, 3, {
    reader: async () =>
      page("https://example.org/SYNTHETIC/", "SYNTHETIC outside"),
    pause: async () => {},
  });
  expect(data.coverage.retrieved).toBe(0);
  expect(data.pages[0]).toMatchObject({ status: "failed" });
});
test("deadline stops further requests, and a large frontier is explicitly truncated", async () => {
  let now = 0;
  const data = await siteReview(root, 60, {
    now: () => now,
    reader: async (url) => {
      now = 190000;
      return page(
        url,
        Array.from(
          { length: 270 },
          (_, i) => `<a href="p-${i}">SYNTHETIC ${i}</a>`,
        ).join(""),
      );
    },
    pause: async () => {},
  });
  expect(data.coverage.stopReason).toBe("time_limit");
  expect(data.coverage.frontierTruncated).toBe(true);
  expect(data.pages.length).toBeLessThanOrEqual(250);
  expect(data.coverage.pending).toBeGreaterThan(0);
});
