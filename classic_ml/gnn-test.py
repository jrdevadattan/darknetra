import numpy as np
from predict import predict

features   = np.load(r"D:\code\python\chd\eth_features.npy")
edge_index = np.load(r"D:\code\python\chd\eth_edge_index.npy")

result = predict(features=features, edge_index=edge_index, node_index=1)
print(result)