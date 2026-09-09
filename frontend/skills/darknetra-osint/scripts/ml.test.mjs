import { afterEach, expect, it } from "vitest";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import {
  featureNames,
  mlPredict,
  mlSchema,
  mlStatus,
  validateMlInput,
} from "./ml.mjs";

const originalInput = process.env.DARKNETRA_INPUT_DIR;
const folders = [];
afterEach(async () => {
  if (originalInput === undefined) delete process.env.DARKNETRA_INPUT_DIR;
  else process.env.DARKNETRA_INPUT_DIR = originalInput;
  for (const folder of folders.splice(0))
    await rm(folder, { recursive: true, force: true });
});
const graph = () => ({
  feature_space: "elliptic-raw-102-v1",
  feature_names: [...featureNames],
  features: [Array(102).fill(0.1), Array(102).fill(0.2)],
  edge_index: [[0], [1]],
  node_index: 1,
  target_id: "SYNTHETIC-TX-2",
  synthetic: true,
});

it("accepts the original graph contract and rejects missing, reordered or unsafe inputs", () => {
  expect(validateMlInput(graph()).node_index).toBe(1);
  expect(mlSchema().feature_names).toHaveLength(102);
  for (const patch of [
    { feature_space: "already-scaled" },
    { features: [[1, 2]] },
    { features: [Array(102).fill(NaN)] },
    { features: [Array(102).fill(Infinity)] },
    { features: [Array(102).fill(1e100)] },
    { features: [Array(102).fill("1")] },
    { features: Array.from({ length: 2001 }, () => Array(102).fill(0)) },
    { edge_index: [[0], [2]] },
    { edge_index: [[0.1], [1]] },
    { edge_index: [[0], []] },
    { edge_index: [[-1], [1]] },
    { edge_index: [[true], [1]] },
    { edge_index: [Array(20001).fill(0), Array(20001).fill(1)] },
    { node_index: -1 },
    { node_index: 2 },
    { node_index: true },
    { feature_names: [...featureNames].reverse() },
    { synthetic: "false" },
  ])
    expect(() => validateMlInput({ ...graph(), ...patch })).toThrow();
  expect(() => validateMlInput({ address: "SYNTHETIC-address" })).toThrow();
  expect(
    validateMlInput({ ...graph(), edge_index: [[], []] }).edge_index,
  ).toEqual([[], []]);
});

it("reads only this chat's upload, keeps its hash and passes validated data to the model", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "SYNTHETIC-ml-"));
  folders.push(root);
  const inputs = path.join(root, "SYNTHETIC-graph.json");
  const body = JSON.stringify(graph());
  await writeFile(inputs, body);
  process.env.DARKNETRA_INPUT_DIR = root;
  let calls = 0;
  const run = async (action, payload) => {
    calls++;
    expect(action).toBe("predict");
    expect(payload.features).toEqual(graph().features);
    expect(payload.node_index).toBe(1);
    expect(payload.edge_index).toEqual([[0], [1]]);
    return {
      prediction: "licit",
      illicit_probability: 0.1,
      licit_probability: 0.9,
      threshold: 0.7166666666666667,
      n_nodes: 2,
      n_edges: 1,
    };
  };
  const result = await mlPredict("SYNTHETIC-graph.json", { run });
  expect(result.sha256).toBe(createHash("sha256").update(body).digest("hex"));
  expect(result.text).toContain("SYNTHETIC demonstration only");
  expect(result.illicit_probability).toBe(0.1);
  expect(await readFile(inputs, "utf8")).toBe(body);
  await expect(mlPredict("../elsewhere.json", { run })).rejects.toThrow();
  await expect(mlPredict(inputs, { run })).rejects.toThrow();
  await writeFile(path.join(root, "SYNTHETIC-bad.json"), '{"features": []}');
  await expect(mlPredict("SYNTHETIC-bad.json", { run })).rejects.toThrow();
  await writeFile(
    path.join(root, "SYNTHETIC-pickle.pkl"),
    Buffer.from([128, 4, 255]),
  );
  await expect(mlPredict("SYNTHETIC-pickle.pkl", { run })).rejects.toThrow();
  expect(calls).toBe(1);
});

it("reports missing model runtimes honestly without leaking local paths", async () => {
  const status = await mlStatus({
    env: {
      DARKNETRA_ML_PYTHON: path.join(
        tmpdir(),
        "SYNTHETIC-missing-python-00000",
      ),
    },
  });
  expect(status.available).toBe(false);
  expect(JSON.stringify(status)).not.toContain("SYNTHETIC-missing-python");
});
