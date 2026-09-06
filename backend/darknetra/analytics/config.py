"""Versioned engineering rankings. Scores are not probabilities of conduct."""

from dataclasses import asdict, dataclass, field

from darknetra.audit.service import digest


@dataclass(frozen=True)
class LinkConfig:
    version: str = "link-v1"
    max_pairs: int = 5000
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "pgp_fingerprint": 0.25,
            "wallet_reuse": 0.18,
            "contact_reuse": 0.15,
            "image_family": 0.15,
            "stylometry": 0.10,
            "rare_phrase": 0.07,
            "temporal": 0.05,
            "operational": 0.05,
            "contradiction": -0.15,
        }
    )

    def digest(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class ActivityConfig:
    version: str = "activity-v1"

    def digest(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class TrendConfig:
    version: str = "trend-v1"
    baseline_days: int = 14
    threshold: float = 3.0

    def digest(self) -> str:
        return digest(asdict(self))
