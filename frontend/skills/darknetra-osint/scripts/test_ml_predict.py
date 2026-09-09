"""CPU integration checks using only SYNTHETIC graphs, no network or case data.

Run in the bundled Python 3.12 runtime; test inference against the original predictor.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import unittest

spec = importlib.util.spec_from_file_location("worker", Path(__file__).with_name("ml_predict.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class SyntheticInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.config, cls.manifest = worker.load_reviewed_model()
        cls.payload = {"features": [[(i + j * 3) / 100 for i in range(102)] for j in range(4)], "edge_index": [[0, 1, 2], [1, 2, 3]], "node_index": 2, "synthetic": True, "target_id": "SYNTHETIC-TX-3"}

    def test_actual_checkpoint_matches_reference_predictor(self):
        result = worker.execute("predict", self.payload)
        expected = self.module.predict(self.payload["features"], self.payload["edge_index"], 2)
        for field in expected:
            self.assertEqual(result[field], expected[field])
        self.assertEqual(result["threshold"], 0.7166666666666667)
        self.assertEqual(result["n_nodes"], 4)
        self.assertEqual(result["n_edges"], 3)
        self.assertEqual(result["model"]["weights_sha256"], self.manifest["sha256"]["models/graphsage_temporal_best.pt"])
        self.assertEqual(worker.execute("predict", self.payload)["illicit_probability"], result["illicit_probability"])

    def test_ready_means_real_assets_load_and_empty_graph_warns(self):
        self.assertTrue(worker.execute("status")["available"])
        result = worker.execute("predict", {**self.payload, "edge_index": [[], []]})
        self.assertIn("No graph edges", result["warnings"][-1])
        self.assertNotEqual(result["illicit_probability"], worker.execute("predict", self.payload)["illicit_probability"])

    def test_bad_dimensions_and_edges_never_return_a_score(self):
        for patch in ({"features": [[0] * 94]}, {"edge_index": [[0], [99]]}, {"node_index": -1}, {"features": [[float("nan")] * 102]}):
            with self.assertRaises(worker.ModelError):
                worker.execute("predict", {**self.payload, **patch})

    def test_changed_artifact_is_rejected_before_import(self):
        original = worker.BASE
        with tempfile.TemporaryDirectory(prefix="SYNTHETIC-model-") as folder:
            copy = Path(folder) / "bundle"
            shutil.copytree(original, copy)
            (copy / "predict.py").write_text("raise AssertionError('SYNTHETIC code must never run')", encoding="utf-8")
            worker.BASE = copy
            try:
                with self.assertRaisesRegex(worker.ModelError, "integrity"):
                    worker.load_reviewed_model()
            finally:
                worker.BASE = original

    def test_fresh_runtime_without_a_writable_temp_directory(self):
        source = """
import importlib.util, json, sys, tempfile
def unavailable():
    raise FileNotFoundError('SYNTHETIC read-only environment has no writable temp directory')
tempfile.gettempdir = unavailable
spec = importlib.util.spec_from_file_location('worker', sys.argv[1])
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
print(json.dumps(worker.execute('predict', json.load(sys.stdin))))
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", source, str(Path(__file__).with_name("ml_predict.py"))], input=json.dumps(self.payload), capture_output=True, text=True, timeout=60, check=True)
        actual = json.loads(result.stdout)
        expected = self.module.predict(self.payload["features"], self.payload["edge_index"], 2)
        self.assertAlmostEqual(actual["illicit_probability"], expected["illicit_probability"], places=7)


if __name__ == "__main__":
    unittest.main()
