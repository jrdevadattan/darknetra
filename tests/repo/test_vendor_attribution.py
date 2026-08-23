from pathlib import Path

from scripts.check_repo_contract import check_vendor_attribution


def test_dashboard_vendor_attribution_is_pinned_and_licensed() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    violations = check_vendor_attribution(repo_root)
    assert violations == []


def test_vendor_attribution_reports_plan_defined_error_labels(tmp_path: Path) -> None:
    assert check_vendor_attribution(tmp_path) == [
        "missing upstream MIT license",
        "missing vendor provenance",
    ]
