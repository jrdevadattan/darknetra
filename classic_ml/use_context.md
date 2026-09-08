# GraphSAGE Cryptocurrency Transaction Classifier
## Model Specifications
Model exists: True        
Config exists: True                       
Model configuration:                
model: GraphSAGE
feature_type: 94 local + 8 temporal graph features
input_features: 102
hidden_dim: 512
dropout: 0.4
learning_rate: 0.001
weight_decay: 0.001
loss: focal_loss
gamma: 2.0
threshold: 0.7166666666666667
validation_f1: 0.8475073313782991
test_f1: 0.581
test_pr_auc: 0.4808
test_accuracy: 0.9512
Weights loaded successfully!
Number of parameter tensors: 19
Total parameters: 635908


## 1. Overview

This repository contains a trained **GraphSAGE Graph Neural Network (GNN)** for classifying cryptocurrency transactions as:

- `0` = licit
- `1` = illicit

The model was trained on the **Elliptic Bitcoin Transaction Dataset**.

The GNN is the ML detection component of the larger application. A Qwen3-class SLM can be placed above it as an **agent/reasoning and explanation layer**, but the SLM does not replace the GNN and does not generate the GNN's numerical prediction.

---

# 2. Dataset

The model uses the Elliptic Bitcoin transaction dataset.

Dataset statistics used in the project:

| Property | Value |
|---|---:|
| Nodes / transactions | 203,769 |
| Directed edges | 234,355 |
| Time steps | 49 |
| Licit labeled transactions | 42,019 |
| Illicit labeled transactions | 4,545 |
| Unknown / unlabeled | 157,205 |
| Original feature columns | 166 |

The dataset is represented by three CSV files.

```text
elliptic_txs_features.csv
elliptic_txs_classes.csv
elliptic_txs_edgelist.csv
```

---

# 3. CSV files

## `elliptic_txs_features.csv`

Contains transaction-level features.

The original dataset contains:

```text
f_0 ... f_165
```

The trained model uses only:

```text
f_0 ... f_93
```

That is **94 local features**.

The remaining original columns are not directly used by this trained GraphSAGE model.

---

## `elliptic_txs_classes.csv`

Contains the transaction labels.

The original class mapping is:

```text
1 -> illicit
2 -> licit
unknown -> unlabeled
```

For model training this was converted to:

```text
illicit -> 1
licit   -> 0
unknown -> -1
```

Unknown transactions are not treated as licit transactions.

---

## `elliptic_txs_edgelist.csv`

Contains the transaction graph.

Each edge represents a transaction relationship / flow:

```text
source_node -> destination_node
```

GraphSAGE uses this graph structure during message passing.

---

# 4. Model input: exactly 102 features

The trained GraphSAGE model expects:

```text
102 features per node
```

These are:

```text
94 local features
+
8 temporal graph features
=
102 features
```

## Local features

The first 94 inputs are:

```text
f_0
f_1
...
f_93
```

from `elliptic_txs_features.csv`.

## Temporal graph features

The additional 8 features are:

```text
hist_in_degree
hist_out_degree
hist_degree
hist_in_out_ratio
hist_neighbor_degree
log_hist_degree
log_hist_in_degree
log_hist_out_degree
```

These features capture historical graph activity available up to the transaction's timestep.

### Feature meanings

`hist_in_degree`
: Historical incoming connectivity.

`hist_out_degree`
: Historical outgoing connectivity.

`hist_degree`
: Historical total connectivity.

`hist_in_out_ratio`
: Ratio between historical incoming and outgoing activity.

`hist_neighbor_degree`
: Historical connectivity/activity of neighboring nodes.

`log_hist_degree`
: Log-scaled historical total degree.

`log_hist_in_degree`
: Log-scaled historical incoming degree.

`log_hist_out_degree`
: Log-scaled historical outgoing degree.

---

# 5. Feature order is IMPORTANT

The input feature order must remain exactly:

```text
[f_0 ... f_93,
 hist_in_degree,
 hist_out_degree,
 hist_degree,
 hist_in_out_ratio,
 hist_neighbor_degree,
 log_hist_degree,
 log_hist_in_degree,
 log_hist_out_degree]
```

Do not reorder the columns.

Do not add or remove features.

The model expects:

```text
(N, 102)
```

where `N` is the number of nodes in the graph context.

---

# 6. Scaling

The model was trained using a `sklearn.preprocessing.StandardScaler`.

The exact trained scaler is:

```text
models/temporal_scaler.pkl
```

It was fitted with:

```text
102 features
```

During inference:

```text
raw 102 features
        ↓
saved StandardScaler
        ↓
scaled 102 features
        ↓
GraphSAGE
```

**Never fit a new scaler during inference.**

Use:

```text
temporal_scaler.pkl
```

from the model package.

---

# 7. Temporal split

The dataset was split chronologically:

```text
Training:   timestep <= 34
Validation: timesteps 35–38
Testing:    timesteps 39–49
```

This is a time-based evaluation rather than a random train/test split.

---

# 8. GraphSAGE architecture

The trained model is **GraphSAGE**.

Architecture:

```text
Input: 102
   |
SAGEConv(102 -> 512, max aggregation)
   |
BatchNorm
   |
ReLU
   |
Dropout(0.4)
   |
SAGEConv(512 -> 512, max aggregation)
   |
BatchNorm
   |
ReLU
   |
Dropout(0.4)
   |
SAGEConv(512 -> 2, max aggregation)
   |
Output logits
```

Output classes:

```text
class 0 -> licit
class 1 -> illicit
```

Total parameters:

```text
635,908
```

---

# 9. Training configuration

```text
Model:           GraphSAGE
Input dimension: 102
Hidden dimension: 512
Layers:          3 GraphSAGE convolution layers
Aggregation:     max
Dropout:         0.4
Optimizer:       AdamW
Learning rate:   0.001
Weight decay:    0.001
Loss:            Focal Loss
Focal gamma:     2.0
```

Focal Loss was used because the illicit class is much smaller than the licit class.

---

# 10. Model files

The required inference files are:

```text
models/
├── graphsage_temporal_best.pt
├── graphsage_temporal_config.json
└── temporal_scaler.pkl
```

Additional reference files:

```text
temporal_feature_names.txt
temporal_X_scaled.npy
```

### Do not use old model artifacts

These are old/invalid artifacts and should not be used:

```text
graphsage_current.pt
config_current.json
scaler_current.pkl
graphsage_temporal_scaler.pkl
```

---

# 11. Model configuration

`graphsage_temporal_config.json` stores the important inference configuration.

Current values:

```json
{
  "model": "GraphSAGE",
  "feature_type": "94 local + 8 temporal graph features",
  "input_features": 102,
  "hidden_dim": 512,
  "dropout": 0.4,
  "learning_rate": 0.001,
  "weight_decay": 0.001,
  "loss": "focal_loss",
  "gamma": 2.0,
  "threshold": 0.7166666666666667
}
```

---

# 12. Classification threshold

The trained decision threshold is:

```text
0.7166666666666667
```

The model first produces:

```text
licit probability
illicit probability
```

Then:

```python
if illicit_probability >= 0.7166666666666667:
    prediction = "illicit"
else:
    prediction = "licit"
```

Do not silently replace this threshold with `0.5`.

---

# 13. Reference predictor

The repository contains:

```text
predict.py
```

It provides the inference interface:

```python
predict(features, edge_index, node_index)
```

The reference predictor:

1. Loads the GraphSAGE configuration.
2. Creates the GraphSAGE architecture.
3. Loads the trained `.pt` weights.
4. Loads the trained StandardScaler.
5. Validates the input dimensions.
6. Scales the features.
7. Creates a PyTorch Geometric graph.
8. Runs GraphSAGE inference.
9. Converts logits to probabilities.
10. Applies the trained threshold.
11. Returns the prediction and probabilities.

---

# 14. `predict()` input parameters

The function requires exactly three inputs:

```python
predict(
    features,
    edge_index,
    node_index
)
```

## `features`

Type:

```python
numpy.ndarray
```

Shape:

```text
(N, 102)
```

Where:

```text
N = number of nodes in the supplied graph context
102 = features per node
```

Example:

```python
features = np.array([
    [0.1] * 102,
    [0.2] * 102,
    [0.3] * 102
], dtype=np.float32)
```

---

## `edge_index`

Type:

```python
numpy.ndarray
```

Shape:

```text
(2, E)
```

Where:

```text
E = number of edges
```

Row 0 contains source node indices.

Row 1 contains destination node indices.

Example:

```python
edge_index = np.array([
    [0, 1, 2],
    [1, 2, 0]
], dtype=np.int64)
```

This represents:

```text
0 -> 1
1 -> 2
2 -> 0
```

---

## `node_index`

Type:

```python
int
```

This is the index of the node/transaction that should be classified.

Example:

```python
node_index = 2
```

The valid range is:

```text
0 <= node_index < N
```

---

# 15. How to use the model end-to-end

This section shows the complete, concrete steps to go from raw CSV data to a prediction.

---

## Step 1 — load the raw data

```python
import pandas as pd
import numpy as np

df_feat  = pd.read_csv("data/elliptic_txs_features.csv", header=None)
df_cls   = pd.read_csv("data/elliptic_txs_classes.csv")
df_edges = pd.read_csv("data/elliptic_txs_edgelist.csv")

# name the columns
n_feat = df_feat.shape[1] - 2
df_feat.columns = ['txId', 'timestep'] + [f'f_{i}' for i in range(n_feat)]

df = df_feat.merge(df_cls, on='txId', how='left')
```

---

## Step 2 — pick a target transaction

```python
target_tx = "some_transaction_id"   # the txId you want to classify
```

---

## Step 3 — build the neighborhood (graph context)

GraphSAGE needs the target node AND its neighbors to do message passing.
Pull the direct 1-hop neighbors from the edgelist.

```python
# all edges where the target is source or destination
neighbor_edges = df_edges[
    (df_edges['txId1'] == target_tx) |
    (df_edges['txId2'] == target_tx)
]

# collect all involved txIds
context_ids = set([target_tx])
context_ids.update(neighbor_edges['txId1'].tolist())
context_ids.update(neighbor_edges['txId2'].tolist())
context_ids = list(context_ids)

# keep only txIds that exist in the feature dataframe
context_ids = [tx for tx in context_ids if tx in set(df_feat['txId'].values)]
```

---

## Step 4 — re-index nodes to 0…N-1

`edge_index` must use integer positions (0, 1, 2 …), not raw txId strings.

```python
local_idx = {tx: i for i, tx in enumerate(context_ids)}
target_node_index = local_idx[target_tx]   # this is what you pass as node_index
```

---

## Step 5 — build edge_index

```python
src_list, dst_list = [], []
for _, row in neighbor_edges.iterrows():
    s, d = row['txId1'], row['txId2']
    if s in local_idx and d in local_idx:
        src_list.append(local_idx[s])
        dst_list.append(local_idx[d])

edge_index = np.array([src_list, dst_list], dtype=np.int64)
# shape: (2, E)  — row 0 = sources, row 1 = destinations
```

If the target transaction has no neighbors at all (isolated node), use an empty edge list:

```python
edge_index = np.empty((2, 0), dtype=np.int64)
```

---

## Step 6 — extract the 94 local features

```python
context_df = df_feat[df_feat['txId'].isin(context_ids)].copy()
context_df = context_df.set_index('txId').reindex(context_ids)

local_cols = [f'f_{i}' for i in range(94)]
X_local = context_df[local_cols].fillna(0).values.astype(np.float32)
# shape: (N, 94)
```

---

## Step 7 — compute the 8 temporal graph features

These must be computed the same way as during training (historical degree counts up to each node's timestep).

```python
# use the FULL edgelist to compute historical degrees
all_tx_list = df_feat['txId'].values
all_tx_idx  = {tx: i for i, tx in enumerate(all_tx_list)}

full_src = [all_tx_idx[tx] for tx in df_edges['txId1'] if tx in all_tx_idx]
full_dst = [all_tx_idx[tx] for tx in df_edges['txId2'] if tx in all_tx_idx]

full_src = np.array(full_src, dtype=np.int32)
full_dst = np.array(full_dst, dtype=np.int32)

src_time = df_feat['timestep'].values[full_src]
dst_time = df_feat['timestep'].values[full_dst]
edge_time = np.maximum(src_time, dst_time)

n_all = len(df_feat)
temporal_features = {}

for tx in context_ids:
    if tx not in all_tx_idx:
        temporal_features[tx] = np.zeros(8, dtype=np.float32)
        continue

    t = df_feat.loc[df_feat['txId'] == tx, 'timestep'].values[0]
    mask = edge_time <= t
    s = full_src[mask]
    d = full_dst[mask]

    in_deg  = np.bincount(d, minlength=n_all).astype(np.float32)
    out_deg = np.bincount(s, minlength=n_all).astype(np.float32)
    total   = in_deg + out_deg

    node_i = all_tx_idx[tx]
    hi  = in_deg[node_i]
    ho  = out_deg[node_i]
    hd  = total[node_i]
    hr  = hi / (ho + 1.0)

    # neighbor degree (undirected)
    nbr_sum   = np.zeros(n_all, dtype=np.float32)
    nbr_count = np.zeros(n_all, dtype=np.float32)
    np.add.at(nbr_sum,   s, total[d])
    np.add.at(nbr_sum,   d, total[s])
    np.add.at(nbr_count, s, 1)
    np.add.at(nbr_count, d, 1)
    hnd = (nbr_sum / np.maximum(nbr_count, 1))[node_i]

    temporal_features[tx] = np.array([
        hi, ho, hd, hr, hnd,
        np.log1p(hd),
        np.log1p(hi),
        np.log1p(ho),
    ], dtype=np.float32)

X_temporal = np.stack(
    [temporal_features[tx] for tx in context_ids],
    axis=0
).astype(np.float32)
# shape: (N, 8)
```

---

## Step 8 — assemble the full feature matrix

```python
X_raw = np.hstack([X_local, X_temporal]).astype(np.float32)
# shape: (N, 102)
```

The column order must be exactly:

```text
[f_0 … f_93,
 hist_in_degree, hist_out_degree, hist_degree, hist_in_out_ratio,
 hist_neighbor_degree, log_hist_degree, log_hist_in_degree, log_hist_out_degree]
```

Do not reorder.

---

## Step 9 — call predict()

```python
from predict import predict

result = predict(
    features=X_raw,        # (N, 102) raw unscaled features
    edge_index=edge_index, # (2, E)   re-indexed integer edges
    node_index=target_node_index  # int  position of target in X_raw
)

print(result)
```

`predict()` applies the saved scaler internally — pass **raw unscaled features**.

---

## Step 10 — read the result

```python
{
    "prediction":          "illicit",   # or "licit"
    "class":               1,           # 0 = licit, 1 = illicit
    "probability":         0.91,        # probability of the returned class
    "licit_probability":   0.09,
    "illicit_probability": 0.91,
    "threshold":           0.7166666666666667
}
```

Flag the transaction as illicit if `illicit_probability >= threshold`.

---

# 16. Example inference (minimal synthetic data)

```python
{
    "prediction": "licit",
    "class": 0,
    "probability": 0.9917,
    "licit_probability": 0.9917,
    "illicit_probability": 0.0083,
    "threshold": 0.7166666666666667
}
```

---

# 17. Output parameters

`predict()` returns:

```text
prediction
class
probability
licit_probability
illicit_probability
threshold
```

Example:

```python
{
    "prediction": "illicit",
    "class": 1,
    "probability": 0.91,
    "licit_probability": 0.09,
    "illicit_probability": 0.91,
    "threshold": 0.7166666666666667
}
```

Interpretation:

```text
class 0 = licit
class 1 = illicit
```

`probability` is the probability corresponding to the returned class.

---

# 18. Very important: GraphSAGE needs graph context

This is a **graph model**, not a normal standalone tabular classifier.

The predictor needs:

```text
features
+
edge_index
+
target node index
```

A raw transaction ID alone is not enough.

Conceptually:

```text
Transaction
    |
    +-- 94 local features
    |
    +-- 8 temporal graph features
    |
    +-- graph neighbors
          |
          +-- edges
          |
          +-- neighborhood information
                    |
                    ↓
                GraphSAGE
                    |
                    ↓
            illicit probability
```

The application/agent is responsible for constructing the graph context and the 102-dimensional input.

---

# 19. Real transaction inference pipeline

For a real transaction, the application should produce:

```text
Raw transaction
       ↓
Extract 94 local features
       ↓
Calculate 8 temporal graph features
       ↓
Construct graph context
       ↓
Create features with shape (N, 102)
       ↓
Create edge_index with shape (2, E)
       ↓
Select target node_index
       ↓
predict(features, edge_index, node_index)
       ↓
GraphSAGE result
```

The feature engineering must match the training process.

---

# 20. Qwen3 SLM integration

The SLM is an **additional reasoning layer**, not another classifier replacing GraphSAGE.

Recommended architecture:

```text
                  Transaction
                       |
                       ▼
              Feature/Graph Builder
                       |
                       ▼
                  GraphSAGE
                       |
                       ▼
              Structured ML Result
                       |
                       ▼
                 Qwen3 SLM
                       |
             ┌─────────┼─────────┐
             ▼         ▼         ▼
          Explain   Investigate  Report
```

The SLM receives the actual output of the GNN.

Example:

```json
{
  "transaction_id": "TX123",
  "graphsage": {
    "prediction": "illicit",
    "class": 1,
    "illicit_probability": 0.91,
    "licit_probability": 0.09,
    "threshold": 0.7166666666666667
  }
}
```

The SLM can turn this into a human-readable explanation.

Example:

```text
Risk assessment: HIGH

GraphSAGE classified the transaction as illicit with
91% model probability, which is above the configured
0.7167 decision threshold.

The transaction should be flagged for further investigation.
```

---

# 21. What the SLM should NOT do

The SLM must not:

- invent probabilities
- invent transaction features
- invent graph statistics
- change the GNN prediction
- retrain the GNN
- fit a new scaler
- arbitrarily change the threshold
- claim that a model prediction proves criminal activity

The numerical result should always come from GraphSAGE.

The SLM's job is to:

```text
receive evidence
      ↓
reason about evidence
      ↓
explain evidence
      ↓
produce an investigation response
```

---

# 22. Suggested SLM tool interface

The agent can expose GraphSAGE as a tool:

```python
run_graphsage(
    features,
    edge_index,
    node_index
)
```

The tool internally calls:

```python
predict(
    features,
    edge_index,
    node_index
)
```

The SLM should receive the returned JSON.

For example:

```text
Agent
  |
  |-- build transaction features
  |
  |-- build graph context
  |
  |-- run_graphsage()
  |
  |-- receive probabilities
  |
  └-- explain result
```

This keeps the model implementation isolated from the agent.

---

# 23. Recommended SLM system instructions

Use a system instruction along these lines:

```text
You are a cryptocurrency transaction investigation assistant.

GraphSAGE is the numerical transaction-classification model.

Never invent numerical evidence.

When GraphSAGE is called, use its returned probabilities exactly.

Do not modify the GraphSAGE threshold.

A GraphSAGE prediction is a model-based risk signal, not proof
that a transaction is criminal.

Explain the available evidence clearly.

If required graph/features are missing, state that the evidence
is insufficient instead of guessing.

Distinguish between:
- model prediction
- model probability
- observed transaction data
- analyst interpretation

Do not claim certainty when the model only provides a probability.
```

---

# 24. Performance

The final trained temporal-feature GraphSAGE model achieved:

```text
Test F1:       0.5810
Test PR-AUC:   0.4808
Test Accuracy: 0.9512
```

For the illicit class:

```text
Precision: 0.58
Recall:    0.58
F1:        0.58
```

Test confusion matrix:

```text
                 Predicted
                 Licit  Illicit

Actual Licit     11346    304
Actual Illicit     299    418
```

Because the dataset is imbalanced, **do not describe the model as "95% accurate at detecting illicit transactions."**

The 95.12% number is overall test accuracy.

For illicit detection, F1 and PR-AUC are more informative.

---

# 25. Current model limitation

The temporal feature engineering uses historical graph information up to the transaction timestep.

However, the current trained GNN uses the supplied `edge_index` for message passing.

For a strict production-grade temporal system, the graph passed to the model should contain only information that would have been available at the prediction time.

Therefore this model should currently be treated as a **trained research/hackathon GraphSAGE model with temporal feature engineering**, rather than claiming perfect leakage-free real-time inference.

---

# 26. Project structure

Recommended structure:

```text
project/
│
├── predict.py
├── README.md
├── requirements.txt
│
├── models/
│   ├── graphsage_temporal_best.pt
│   ├── graphsage_temporal_config.json
│   ├── temporal_scaler.pkl
│   └── temporal_feature_names.txt
│
├── data/
│   ├── elliptic_txs_features.csv
│   ├── elliptic_txs_classes.csv
│   └── elliptic_txs_edgelist.csv
│
└── agent/
    ├── slm_agent.py
    ├── tools/
    └── ...
```

---

# 27. Dependencies

The reference predictor requires the Python packages used by the model:

```text
torch
torch-geometric
numpy
scikit-learn
```

Use the project's:

```text
requirements.txt
```

for the exact environment.

The model does not need to be retrained when the application starts.

---

# 28. Quick verification

After installing dependencies and placing the model files correctly:

```bash
python test_predict.py
```

The predictor should successfully load:

```text
graphsage_temporal_best.pt
temporal_scaler.pkl
graphsage_temporal_config.json
```

and return a structured prediction.

---

# 29. What the AI coding agent needs to know

The AI coding agent should treat these files as fixed model artifacts:

```text
predict.py
models/graphsage_temporal_best.pt
models/graphsage_temporal_config.json
models/temporal_scaler.pkl
```

Do not rewrite the GraphSAGE architecture unnecessarily.

Do not retrain the model during application startup.

Do not create another scaler.

Do not change the 102-feature ordering.

Do not change the threshold unless explicitly performing a new model-calibration experiment.

The agent's main integration task is to build the surrounding application:

```text
transaction input
       ↓
feature construction
       ↓
graph construction
       ↓
GraphSAGE inference
       ↓
structured result
       ↓
Qwen3 SLM
       ↓
explanation / investigation workflow
```

---

# 30. One-line summary

**GraphSAGE performs the numerical graph-based illicit-transaction classification; the surrounding application supplies the 102 features and graph context, and a Qwen3-class SLM can use the resulting structured evidence for reasoning, explanation, and agent orchestration.**
