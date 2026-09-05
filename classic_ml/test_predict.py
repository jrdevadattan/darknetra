import numpy as np
from predict import predict

# 5 transactions, each with 102 features
features = np.array([
    [0.10] * 102,
    [0.20] * 102,
    [0.30] * 102,
    [0.40] * 102,
    [0.50] * 102,
], dtype=np.float32)

# Graph:
# 0 -> 1
# 1 -> 2
# 2 -> 3
# 3 -> 4
# 4 -> 0
edge_index = np.array([
    [0, 1, 2, 3, 4],
    [1, 2, 3, 4, 0],
], dtype=np.int64)

# Predict transaction/node 2
result = predict(
    features=features,
    edge_index=edge_index,
    node_index=2
)

print(result)