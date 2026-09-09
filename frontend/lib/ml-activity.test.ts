import { expect, it } from "vitest";
import { commandLabel, helperResult } from "./run-activity";

it("records model output as analysis of the supplied file, with its research limitation", () => {
  const command =
    "node .agents/skills/darknetra-osint/scripts/osint.mjs ml-predict 'SYNTHETIC-graph.json'";
  const data = {
    file: "SYNTHETIC-graph.json",
    sha256: "a".repeat(64),
    analysis: "graphsage",
    synthetic: true,
    text: "SYNTHETIC research model output. Not proof of wrongdoing. Illicit-class score: 0.1; fixed threshold: 0.7166666666666667.",
  };
  const activity = helperResult(command, JSON.stringify({ ok: true, data }));
  expect(activity.sources).toHaveLength(1);
  expect(activity.sources?.[0]).toMatchObject({
    file: data.file,
    sha256: data.sha256,
    status: "analysed",
    kind: "file",
    excerpt: data.text,
  });
  expect(activity.sources?.[0].title).toContain("SYNTHETIC");
  expect(activity.sources?.[0].url).toBeUndefined();
  expect(activity.result).toBe(data.text);
  expect(commandLabel(command)).toBe("Analysing a transaction graph");
  expect(
    helperResult(
      command,
      JSON.stringify({ ok: false, error: { code: "MODEL_UNAVAILABLE" } }),
    ).sources,
  ).toBeUndefined();
});
