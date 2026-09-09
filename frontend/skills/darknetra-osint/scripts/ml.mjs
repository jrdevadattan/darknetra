import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { inputFile } from "./files.mjs";

const fail = (code, message) => Object.assign(new Error(message), { code });
export const featureNames = [
  ...Array.from({ length: 94 }, (_, i) => `f_${i}`),
  "hist_in_degree",
  "hist_out_degree",
  "hist_degree",
  "hist_in_out_ratio",
  "hist_neighbor_degree",
  "log_hist_degree",
  "log_hist_in_degree",
  "log_hist_out_degree",
];
export function mlSchema() {
  return {
    model: "GraphSAGE",
    feature_space: "elliptic-raw-102-v1",
    feature_names: featureNames,
    required: {
      feature_space: "elliptic-raw-102-v1",
      features: "N rows of 102 finite unscaled numbers in feature_names order",
      edge_index:
        "[source_indices, destination_indices], two equal-length integer arrays; directed edges",
      node_index: "Integer target transaction index from 0 to N-1",
    },
    optional: {
      feature_names: "When supplied, must exactly match this order",
      target_id: "Transaction reference supplied with this graph",
      synthetic: "true for demonstration data; never use it for case findings",
    },
    limits: { nodes: 2000, edges: 20000, file_bytes: 8 * 1024 * 1024 },
    note: "A wallet address or transaction ID alone is insufficient. Supply training-compatible Elliptic features and graph context; do not guess features, substitute zeros or rescale them. The helper applies the saved scaler once. No raw-chain feature extractor is available.",
  };
}
export function validateMlInput(data) {
  if (!data || typeof data !== "object" || Array.isArray(data))
    throw fail("VALIDATION", "Upload a JSON object matching ml-schema.");
  if (data.feature_space !== "elliptic-raw-102-v1")
    throw fail(
      "VALIDATION",
      "Set feature_space to elliptic-raw-102-v1 only for unscaled, training-compatible features. Run ml-schema for the required input.",
    );
  if (
    data.feature_names !== undefined &&
    (!Array.isArray(data.feature_names) ||
      data.feature_names.length !== 102 ||
      data.feature_names.some((n, i) => n !== featureNames[i]))
  )
    throw fail(
      "VALIDATION",
      "feature_names must match the original model's 102-feature order.",
    );
  if (
    !Array.isArray(data.features) ||
    !data.features.length ||
    data.features.length > 2000 ||
    data.features.some(
      (row) =>
        !Array.isArray(row) ||
        row.length !== 102 ||
        row.some(
          (n) =>
            typeof n !== "number" ||
            !Number.isFinite(n) ||
            Math.abs(n) > 3.402823466e38,
        ),
    )
  )
    throw fail(
      "VALIDATION",
      "features must contain 1–2000 rows of exactly 102 finite float32-compatible numbers.",
    );
  const n = data.features.length;
  if (
    !Array.isArray(data.edge_index) ||
    data.edge_index.length !== 2 ||
    data.edge_index.some((row) => !Array.isArray(row)) ||
    data.edge_index[0].length !== data.edge_index[1].length ||
    data.edge_index[0].length > 20000 ||
    data.edge_index.some((row) =>
      row.some((i) => !Number.isInteger(i) || i < 0 || i >= n),
    )
  )
    throw fail(
      "VALIDATION",
      "edge_index must contain two equal-length arrays of valid node indices, with at most 20000 directed edges.",
    );
  if (
    !Number.isInteger(data.node_index) ||
    data.node_index < 0 ||
    data.node_index >= n
  )
    throw fail(
      "VALIDATION",
      "node_index must identify a transaction row in features.",
    );
  if (data.synthetic !== undefined && typeof data.synthetic !== "boolean")
    throw fail("VALIDATION", "synthetic must be true or false.");
  if (
    data.target_id !== undefined &&
    (typeof data.target_id !== "string" ||
      data.target_id.length > 200 ||
      /[\x00-\x1f\x7f]/.test(data.target_id))
  )
    throw fail(
      "VALIDATION",
      "target_id must be a transaction reference of at most 200 characters.",
    );
  return {
    features: data.features,
    edge_index: data.edge_index,
    node_index: data.node_index,
    synthetic: data.synthetic === true,
    ...(data.target_id ? { target_id: data.target_id } : {}),
  };
}

export function runMl(action, payload, options = {}) {
  const env = options.env || process.env;
  const python =
    env.DARKNETRA_ML_PYTHON ||
    (process.platform === "win32" ? "python" : "python3");
  return new Promise((resolve, reject) => {
    const child = execFile(
      python,
      [
        "-I",
        "-B",
        fileURLToPath(new URL("./ml_predict.py", import.meta.url)),
        action,
      ],
      {
        shell: false,
        windowsHide: true,
        timeout: 60000,
        maxBuffer: 128 * 1024,
        env: Object.fromEntries(
          Object.entries({
            PATH: env.PATH || env.Path,
            SYSTEMROOT: env.SYSTEMROOT || env.SystemRoot,
            WINDIR: env.WINDIR,
            PYTHONDONTWRITEBYTECODE: "1",
            OMP_NUM_THREADS: "2",
            OPENBLAS_NUM_THREADS: "2",
            MKL_NUM_THREADS: "2",
          }).filter(([, v]) => v !== undefined),
        ),
      },
      (error, stdout) => {
        let response;
        try {
          response = JSON.parse(stdout);
        } catch {
          /* Never expose Python diagnostics or local paths. */
        }
        if (
          response?.ok === false &&
          ["VALIDATION", "MODEL_UNAVAILABLE", "MODEL_INCOMPATIBLE"].includes(
            response.error?.code,
          )
        )
          return reject(fail(response.error.code, response.error.message));
        if (error || response?.ok !== true)
          return reject(
            fail(
              "MODEL_UNAVAILABLE",
              "The local model runtime is unavailable or exceeded its one-minute limit. Use the Docker app or configure its Python 3.12 runtime.",
            ),
          );
        resolve(response.data);
      },
    );
    child.stdin.on("error", () => {});
    child.stdin.end(payload ? JSON.stringify(payload) : "");
  });
}
export async function mlStatus(options = {}) {
  try {
    return await (options.run || runMl)("status", undefined, options);
  } catch (error) {
    return {
      available: false,
      model: "GraphSAGE",
      command: "ml-predict <uploaded-json-file>",
      reason: error.message,
    };
  }
}
export async function mlPredict(name, options = {}) {
  const { file, size } = await inputFile(name);
  if (size > 8 * 1024 * 1024)
    throw fail("SIZE_LIMIT", "Model input must be at most 8 MiB.");
  const bytes = await readFile(file);
  if (bytes.length > 8 * 1024 * 1024)
    throw fail("SIZE_LIMIT", "Model input must be at most 8 MiB.");
  let data;
  try {
    data = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw fail(
      "VALIDATION",
      "Model input must be a UTF-8 JSON file, not a checkpoint, pickle or executable.",
    );
  }
  const payload = validateMlInput(data);
  const result = await (options.run || runMl)("predict", payload, options);
  const prefix = payload.synthetic ? "SYNTHETIC demonstration only. " : "";
  const scope = `${prefix}Research model output for a supplied transaction graph. Not proof of wrongdoing, wallet ownership or sanctions exposure. Reported illicit-class test F1: 0.581; this does not validate performance on this input.`;
  return {
    file: name,
    size: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    analysis: "graphsage",
    ...result,
    synthetic: payload.synthetic,
    ...(payload.target_id ? { target_id: payload.target_id } : {}),
    scope,
    text: `${scope}\nTarget row: ${payload.node_index}${payload.target_id ? ` (${payload.target_id})` : ""}. Model class: ${result.prediction}. Illicit-class score: ${result.illicit_probability}; licit-class score: ${result.licit_probability}; fixed threshold: ${result.threshold}. Nodes: ${result.n_nodes}; directed edges: ${result.n_edges}. Input features were supplied, not independently verified.`,
  };
}
