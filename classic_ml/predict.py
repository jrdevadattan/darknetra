from pathlib import Path
import json
import pickle
import numpy as np
import torch
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"

MODEL_PATH = MODEL_DIR / "graphsage_temporal_best.pt"
SCALER_PATH = MODEL_DIR / "temporal_scaler.pkl"
CONFIG_PATH = MODEL_DIR / "graphsage_temporal_config.json"


class GraphSAGE(torch.nn.Module):
    def __init__(self, in_dim=102, hidden_dim=512, out_dim=2, dropout=0.4):
        super().__init__()
        self.conv1 = SAGEConv(in_dim, hidden_dim, aggr="max")
        self.bn1 = torch.nn.BatchNorm1d(hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, hidden_dim, aggr="max")
        self.bn2 = torch.nn.BatchNorm1d(hidden_dim)
        self.conv3 = SAGEConv(hidden_dim, out_dim, aggr="max")
        self.dropout = dropout

    def forward(self, data):
        x, edge_index = data.x, data.edge_index

        x = self.conv1(x, edge_index)
        x = self.bn1(x)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)

        x = self.conv2(x, edge_index)
        x = self.bn2(x)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)

        return self.conv3(x, edge_index)


def load_model():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    model = GraphSAGE(
        in_dim=config.get("input_features", 102),
        hidden_dim=config.get("hidden_dim", 512),
        dropout=config.get("dropout", 0.4),
    )

    state_dict = torch.load(
        MODEL_PATH,
        map_location="cpu",
        weights_only=True,
    )
    model.load_state_dict(state_dict)
    model.eval()

    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)

    return model, scaler, config


def predict(features, edge_index, node_index=0):
    """
    Reference interface for the multi-model agent.

    features:
        numpy/list array of shape (number_of_nodes, 102)
        94 local features + 8 temporal graph features.

    edge_index:
        numpy/list array of shape (2, number_of_edges).

    node_index:
        Index of the transaction to classify.
    """

    model, scaler, config = load_model()

    features = np.asarray(features, dtype=np.float32)

    expected = config.get("input_features", 102)
    if features.ndim != 2 or features.shape[1] != expected:
        raise ValueError(
            f"Expected features with shape (N, {expected}), "
            f"received {features.shape}"
        )

    if not 0 <= node_index < len(features):
        raise IndexError("node_index is outside the feature matrix")

    # Same scaler used during training.
    features = scaler.transform(features).astype(np.float32)

    data = Data(
        x=torch.tensor(features, dtype=torch.float32),
        edge_index=torch.as_tensor(edge_index, dtype=torch.long),
    )

    with torch.no_grad():
        probs = torch.softmax(model(data), dim=1)[node_index]

    licit_probability = float(probs[0])
    illicit_probability = float(probs[1])
    threshold = float(config.get("threshold", 0.7166666666666667))

    is_illicit = illicit_probability >= threshold

    return {
        "prediction": "illicit" if is_illicit else "licit",
        "class": 1 if is_illicit else 0,
        "probability": illicit_probability if is_illicit else licit_probability,
        "licit_probability": licit_probability,
        "illicit_probability": illicit_probability,
        "threshold": threshold,
    }


if __name__ == "__main__":
    print("GraphSAGE predictor ready.")
    print("Use: predict(features, edge_index, node_index)")