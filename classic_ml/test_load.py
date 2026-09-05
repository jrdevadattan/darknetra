import torch
import json
from pathlib import Path

MODEL_DIR = Path(r"D:\code\python\chd\models")

model_path = MODEL_DIR / "graphsage_temporal_best.pt"
config_path = MODEL_DIR / "graphsage_temporal_config.json"

print("Model exists:", model_path.exists())
print("Config exists:", config_path.exists())

# Load configuration
with open(config_path, "r") as f:
    config = json.load(f)

print("\nModel configuration:")
for key, value in config.items():
    print(f"{key}: {value}")

# Load weights
state_dict = torch.load(
    model_path,
    map_location="cpu",
    weights_only=True
)

print("\nWeights loaded successfully!")
print("Number of parameter tensors:", len(state_dict))

total_params = sum(
    tensor.numel() for tensor in state_dict.values()
)

print("Total parameters:", total_params)