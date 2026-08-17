from pathlib import Path

from scripts.check_repo_contract import check_vendor_attribution


def test_dashboard_vendor_attribution_is_pinned_and_licensed() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    violations = check_vendor_attribution(repo_root)
    assert violations == []
