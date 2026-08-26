"""Read-only normalization and policy controls for approved OSINT sources."""

from services.collector.darknetra_collector.adapters import (
    IntegrationDefinition,
    NormalizedObservation,
    NormalizedPackage,
    get_integration_catalog,
    normalize_integration_output,
)
from services.collector.darknetra_collector.policy import (
    CollectionRequest,
    CollectorPolicy,
    PolicyViolation,
    ValidatedCollectionRequest,
)

__all__ = [
    "CollectionRequest",
    "CollectorPolicy",
    "IntegrationDefinition",
    "NormalizedObservation",
    "NormalizedPackage",
    "PolicyViolation",
    "ValidatedCollectionRequest",
    "get_integration_catalog",
    "normalize_integration_output",
]
