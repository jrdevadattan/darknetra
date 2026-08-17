import json
from pathlib import Path


def test_root_workspace_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    workspace = (root / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert package["private"] is True
    assert package["packageManager"].startswith("pnpm@10.")
    assert package["engines"]["node"] == ">=24 <25"
    assert "apps/*" in workspace and "packages/*" in workspace
    assert (root / ".node-version").read_text().strip() == "24"
    assert (root / ".python-version").read_text().strip() == "3.12"
