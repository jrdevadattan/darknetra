"""Optional offline sanctions data. Missing or malformed data means unknown."""

import json
from pathlib import Path

from darknetra.api.v1.schemas.analytics import SanctionsAssessment


class OfacList:
    def __init__(self, path=None):
        self.path = (
            Path(path)
            if path
            else Path(__file__).resolve().parents[3] / "data/sanctions/ofac_digital_currency.json"
        )
        self.unavailable_reason = "offline sanctions dataset unavailable"
        self.entries = None
        self.version = None
        try:
            if self.path.stat().st_size > 50 * 1024 * 1024:
                return
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("list_version"), str)
                or not data["list_version"]
            ):
                return
            entries = data.get("entries")
            if not isinstance(entries, list) or any(
                not isinstance(row, dict) or not isinstance(row.get("address"), str)
                for row in entries
            ):
                return
            self.entries, self.version, self.unavailable_reason = (
                entries,
                data["list_version"],
                None,
            )
        except (OSError, ValueError, UnicodeError):
            pass

    def check(self, address):
        if self.entries is None:
            return None
        normalized = address.lower() if address.startswith("0x") else address
        hit = next(
            (
                row
                for row in self.entries
                if (row["address"].lower() if row["address"].startswith("0x") else row["address"])
                == normalized
            ),
            None,
        )
        return SanctionsAssessment(
            sanctioned=hit is not None,
            source="ofac_sdn_offline",
            program=hit.get("program") if hit else None,
            entity=hit.get("entity") if hit else None,
            list_version=self.version,
        )
