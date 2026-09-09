import { expect, test } from "vitest";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { providerIntegrations } from "./provider-integrations";
import { helperResult } from "./run-activity";

test("settings reads the actual CLI configuration without exposing its credentials", async () => {
  const directory = await mkdtemp(
    path.join(tmpdir(), "darknetra-SYNTHETIC-integrations-"),
  );
  const old = process.env.DARKNETRA_PROVIDER_FILE;
  try {
    const file = path.join(directory, "providers.json");
    await writeFile(
      file,
      JSON.stringify({ flashpoint: "SYNTHETIC-private-api-value" }),
    );
    process.env.DARKNETRA_PROVIDER_FILE = file;
    const result = await providerIntegrations();
    expect(result.providers).toHaveLength(4);
    expect(result.providers[0].state).toBe("configured_unverified");
    expect(JSON.stringify(result)).not.toContain("SYNTHETIC-private-api-value");
    expect(JSON.stringify(result)).not.toContain(directory);
  } finally {
    if (old === undefined) delete process.env.DARKNETRA_PROVIDER_FILE;
    else process.env.DARKNETRA_PROVIDER_FILE = old;
    await rm(directory, { force: true, recursive: true });
  }
});
test("provider response becomes a cited run source without asserting the underlying website was retrieved", () => {
  const url =
    "https://api.recordedfuture.com/v2/domain/idn%3Aexample.com?fields=entity%2Crisk%2CintelCard";
  const result = helperResult(
    "node osint.mjs recorded-future 'example.com'",
    JSON.stringify({
      ok: true,
      data: {
        provider: "recorded-future",
        url,
        title: "SYNTHETIC provider assessment",
        fetchedAt: "2026-09-08T10:00:00Z",
        text: "Provider-reported intelligence, not a confirmed finding. SYNTHETIC result.",
      },
    }),
  );
  expect(result.sources).toHaveLength(1);
  expect(result.sources![0]).toMatchObject({
    url,
    title: "SYNTHETIC provider assessment",
    status: "retrieved",
  });
  expect(
    result.sources!.some((source) => source.url === "https://example.com/"),
  ).toBe(false);
});
