"""Fixed classic_ml inference, invoked over stdin by the maintained CLI helper."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent.parent / "assets" / "classic_ml"
REQUIRED = (
    "predict.py", "models/graphsage_temporal_best.pt",
    "models/graphsage_temporal_config.json", "models/temporal_scaler.pkl",
    "models/temporal_feature_names.txt",
)


class ModelError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def load_reviewed_model():
    # PyG imports Dynamo even for eager inference. Its default cache discovery
    # probes writable temp directories, which the CLI's read-only profile denies.
    # Use an existing immutable directory; this predictor never compiles or writes
    # a cache. PyG's optional code-generation path falls back to eager propagation.
    os.environ["TORCHINDUCTOR_CACHE_DIR"] = str(BASE)
    # Never import a predictor or unpickle a scaler from an uploaded path.
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    for name in REQUIRED:
        digest = hashlib.sha256((BASE / name).read_bytes()).hexdigest()
        if digest != manifest["sha256"].get(name):
            raise ModelError("MODEL_INCOMPATIBLE", "The bundled model files failed integrity verification.")
    spec = importlib.util.spec_from_file_location("darknetra_classic_ml", BASE / "predict.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.torch.set_num_threads(2)
    model, scaler, config = module.load_model()
    if config["input_features"] != 102 or scaler.n_features_in_ != 102 or config["threshold"] != 0.7166666666666667:
        raise ModelError("MODEL_INCOMPATIBLE", "The bundled model's input/scaler/threshold contract is incompatible.")
    # Retain the original inference function, with the just-verified assets cached.
    module.load_model = lambda: (model, scaler, config)
    return module, config, manifest


def model_details(module, config, manifest):
    import sklearn
    import torch_geometric
    return {
        "name": "GraphSAGE", "source_commit": manifest["source_commit"],
        "weights_sha256": manifest["sha256"]["models/graphsage_temporal_best.pt"],
        "scaler_sha256": manifest["sha256"]["models/temporal_scaler.pkl"],
        "input_features": 102, "feature_space": "elliptic-raw-102-v1",
        "threshold": config["threshold"],
        "reported_test_metrics": {"illicit_f1": config["test_f1"], "pr_auc": config["test_pr_auc"], "overall_accuracy": config["test_accuracy"]},
        "runtime": {"python": ".".join(map(str, sys.version_info[:3])), "torch": module.torch.__version__, "torch_geometric": torch_geometric.__version__, "scikit_learn": sklearn.__version__, "device": "cpu"},
    }


def execute(action, data=None):
    if sys.version_info[:2] != (3, 12):
        raise ModelError("MODEL_UNAVAILABLE", "This model runtime requires Python 3.12.")
    if action not in ("status", "predict"):
        raise ModelError("VALIDATION", "Use the maintained ml-status or ml-predict CLI command.")
    module, config, manifest = load_reviewed_model()
    details = model_details(module, config, manifest)
    if action == "status":
        return {"available": True, "state": "ready", "command": "ml-predict <uploaded-json-file>", "model": details, "note": "Weights and scaler loaded on CPU; a compatible uploaded graph is required for inference."}
    # Recheck dimensions and bounds before allocating torch tensors, even for a direct invocation.
    if not isinstance(data, dict):
        raise ModelError("VALIDATION", "Supply a graph JSON object through the maintained helper.")
    features, edges, target = data.get("features"), data.get("edge_index"), data.get("node_index")
    number = lambda x: type(x) in (int, float) and math.isfinite(x) and abs(x) <= 3.402823466e38
    if not isinstance(features, list) or not 1 <= len(features) <= 2000 or any(not isinstance(row, list) or len(row) != 102 or not all(map(number, row)) for row in features):
        raise ModelError("VALIDATION", "Expected 1–2000 rows of 102 finite float32 features.")
    n = len(features)
    if not isinstance(edges, list) or len(edges) != 2 or not all(isinstance(row, list) for row in edges) or len(edges[0]) != len(edges[1]) or len(edges[0]) > 20000 or any(type(i) is not int or not 0 <= i < n for row in edges for i in row):
        raise ModelError("VALIDATION", "The directed edge indices are invalid.")
    if type(target) is not int or not 0 <= target < n:
        raise ModelError("VALIDATION", "The target node index is invalid.")
    result = module.predict(features, edges, target)
    if not all(math.isfinite(result[k]) and 0 <= result[k] <= 1 for k in ("licit_probability", "illicit_probability", "probability")) or abs(result["licit_probability"] + result["illicit_probability"] - 1) > 1e-5:
        raise ModelError("MODEL_INCOMPATIBLE", "The model returned non-finite or invalid scores for this input.")
    warnings = ["Input feature semantics and provenance cannot be verified by shape validation.", "This research model has not been validated for live wallet screening; a transaction result is not a wallet assessment.", "The supplied directed graph is used unchanged; its completeness and prediction-time cutoff affect the result."]
    if not edges[0]:
        warnings.append("No graph edges were supplied; the result has no neighbor context.")
    return {**result, "node_index": target, "n_nodes": n, "n_edges": len(edges[0]), "model": details, "warnings": warnings}


if __name__ == "__main__":
    try:
        body = sys.stdin.buffer.read(8 * 1024 * 1024 + 1)
        if len(body) > 8 * 1024 * 1024:
            raise ModelError("VALIDATION", "Model input exceeds 8 MiB.")
        data = json.loads(body) if body else None
        response = {"ok": True, "data": execute(sys.argv[1] if len(sys.argv) == 2 else "", data)}
    except ModelError as error:
        response = {"ok": False, "error": {"code": error.code, "message": str(error)}}
    except (ImportError, FileNotFoundError):
        response = {"ok": False, "error": {"code": "MODEL_UNAVAILABLE", "message": "The model files or Python inference dependencies are missing. Use the rebuilt Docker app."}}
    except Exception:
        response = {"ok": False, "error": {"code": "MODEL_INCOMPATIBLE", "message": "The bundled model could not process this input with the installed runtime."}}
    print(json.dumps(response, allow_nan=False))
    sys.exit(0 if response["ok"] else 1)
