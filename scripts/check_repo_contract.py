from __future__ import annotations

from pathlib import Path

UPSTREAM_REPO = "arhamkhnz/next-shadcn-admin-dashboard"
UPSTREAM_COMMIT = "0c668859c4fdeaa0279c951c178b965cce62a125"


def check_vendor_attribution(repo_root: Path) -> list[str]:
    errors: list[str] = []
    license_path = repo_root / "LICENSES" / "next-shadcn-admin-dashboard-MIT.txt"
    vendor_doc = repo_root / "docs" / "vendor" / "next-shadcn-admin-dashboard.md"

    if not license_path.is_file():
        errors.append("missing upstream MIT license")
    else:
        text = license_path.read_text(encoding="utf-8")
        if "Copyright (c) 2024 Mohammed Arham Khan" not in text:
            errors.append("missing upstream copyright")
        if "MIT License" not in text:
            errors.append("missing MIT license text")

    if not vendor_doc.is_file():
        errors.append("missing vendor provenance")
    else:
        text = vendor_doc.read_text(encoding="utf-8")
        if UPSTREAM_REPO not in text:
            errors.append("missing upstream repo")
        if UPSTREAM_COMMIT not in text:
            errors.append("missing pinned commit")

    return errors
