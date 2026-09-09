# Classic ML transaction model

The original `classic_ml` package is in repository history at `f9e4311f0f6331d05427245be7877651d0a17271`; the current main tree has an optional model adapter, while the trained files were retained locally under `models/gnn`. The original predictor, checkpoint, scaler, config and feature list are bundled unchanged from that historical commit in `assets/classic_ml`. `manifest.json` records their SHA-256 digests; the helper checks them before importing the predictor or loading the trusted scaler. Uploaded model files, pickle files and Python code are never loaded.

## Use through the CLI

Run one command at a time from this chat's working directory:

```sh
node .agents/skills/darknetra-osint/scripts/osint.mjs ml-status
node .agents/skills/darknetra-osint/scripts/osint.mjs ml-schema
node .agents/skills/darknetra-osint/scripts/osint.mjs ml-predict 'uploaded_graph.json'
```

Use the actual filename listed in the attachment context. The input is read only from this chat's inputs folder. `ml-status` verifies the files and loads the actual weights and scaler, without producing a prediction. Docker includes the CPU Python 3.12 environment. A native installation can set `DARKNETRA_ML_PYTHON` to its Python 3.12 executable with the versions from `frontend/research/ml-requirements.txt` and CPU torch 2.11.0 installed.

Inference uses eager CPU execution under the existing read-only CLI profile. The wrapper points optional compiler-cache discovery at the existing model directory; it does not compile, write caches, grant filesystem access or change the predictor. Optional code generation falls back to eager propagation when temporary-file writes are denied.

## Required input

Upload one UTF-8 JSON object with these fields:

| Field | Required value |
| --- | --- |
| `feature_space` | `elliptic-raw-102-v1`, declaring unscaled, training-compatible features |
| `features` | `(N, 102)` numeric matrix: one row per transaction |
| `edge_index` | `(2, E)` integer matrix: first row sources, second row destinations, using zero-based row indices |
| `node_index` | Zero-based index of the transaction to classify |
| `feature_names` | Optional; when supplied must exactly match `ml-schema` |
| `target_id` | Optional transaction reference supplied with the graph |
| `synthetic` | Set `true` for demonstration data; never use synthetic outputs as findings |

Limits: 2,000 nodes, 20,000 directed edges, 8 MiB JSON. Empty edge arrays `[[], []]` are accepted but explicitly warn that neighbor context is absent. Oversized graphs are rejected; no silent sampling or truncation changes the graph.

Feature order is fixed: `f_0` through `f_93`, then `hist_in_degree`, `hist_out_degree`, `hist_degree`, `hist_in_out_ratio`, `hist_neighbor_degree`, `log_hist_degree`, `log_hist_in_degree`, `log_hist_out_degree`.

The 94 local columns come from the Elliptic Bitcoin transaction dataset's feature representation. The eight historical columns must match the training pipeline, including the time cutoff and graph indexing. The helper applies the saved StandardScaler exactly once. Do not supply `temporal_X_scaled.npy` or already-standardized values, fit a new scaler, generate missing columns, or treat numeric shape validation as proof that feature semantics are correct.

There is no validated raw-blockchain-to-Elliptic feature extractor in this package. A wallet address, transaction hash, explorer response or natural-language description is insufficient. Request a compatible graph export from the financial/data analyst, together with its source, preprocessing method, transaction-to-row mapping and as-of cutoff. Do not silently implement a different feature builder: the historical notebook's index mapping and temporal assumptions need a separate validation before adopting it for new data. No class labels are needed for inference.

## How to use the result

`ml-predict` returns the original model's `prediction`, `class`, `probability`, `licit_probability`, `illicit_probability`, and fixed `threshold` of **0.7166666666666667**, plus the target row, node/edge counts, artifact hashes, runtime versions, limitations and input-file SHA-256. The activity timeline and source graph retain this file and its model summary. Cite the attachment filename/hash; do not invent a public URL for local data. The model scores become input for Codex's explanation, not another language model response.

This is the fixed three-layer GraphSAGE research model (102 → 512 → 512 → 2; max aggregation, BatchNorm, dropout disabled during evaluation). Reported test illicit-class F1 is **0.581** and PR-AUC **0.4808**. Overall accuracy **0.9512** is not illicit-detection accuracy. These are historical metrics from the model package, not validation on the user's data; probabilities are model outputs, not established real-world likelihoods.

Use the scores unchanged and distinguish them from observations. An `illicit` class is a model signal for the selected transaction, not proof of criminal conduct, a sanctions match, wallet ownership or a classification of every transaction in a wallet. The supplied directed graph is used unchanged; graph completeness and future information can affect predictions. Synthetic smoke tests establish execution/parity only, not investigative accuracy. Missing dependencies, altered artifacts or incompatible input must remain an unsuccessful check.
