"""Adapters yield references to persisted evidence, never invented captures."""

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from darknetra.crypto.fields import FieldCipher
from darknetra.errors import AppError
from darknetra.evidence.models import Derivative, Evidence
from darknetra.evidence.service import get_evidence, get_text
from darknetra.evidence.vault import LocalVault
from darknetra.monitor.validation import normalize
from darknetra.tools.contracts import ToolError
from darknetra.tools.invoke import invoke


@dataclass(frozen=True)
class Hit:
    evidence_id: UUID
    evidence_code: str
    excerpt: str
    source_class: str
    locator: str
    body_hash: str
    family: str
    event_id: str | None = None
    image_distance: int | None = None


def family_of(evidence) -> str:
    explicit = evidence.meta.get("source_family") if evidence.source_class == "SYNTHETIC" else None
    value = explicit or (
        "locator:" + evidence.locator_bidx if evidence.locator_bidx else "local-evidence"
    )
    return hashlib.sha256(value.encode()).hexdigest()


async def local_hits(session, case, item, settings) -> list[Hit]:
    rows = await session.scalars(
        select(Evidence)
        .where(
            Evidence.case_id == case.id,
            Evidence.status.in_(["READY", "PARTIAL"]),
            Evidence.source_class.in_(case.source_policy["allowed_source_classes"]),
            Evidence.source_class != "REPORT",
        )
        .order_by(Evidence.created_at, Evidence.code)
    )
    hits = []
    for evidence in rows:
        distance = None
        if item.type == "IMAGE_HASH":
            if evidence.kind != "IMAGE":
                continue
            meta = await session.scalar(
                select(Derivative)
                .where(
                    Derivative.case_id == case.id,
                    Derivative.evidence_id == evidence.id,
                    Derivative.kind == "IMAGE_META",
                )
                .order_by(Derivative.version.desc())
                .limit(1)
            )
            if not meta:
                continue
            import json

            with LocalVault(settings.vault_path).open(meta.storage_key) as stream:
                attributes = json.load(stream)
            phash = attributes.get("phash") or attributes.get("pHash")
            if not phash:
                continue
            distance = (int(phash, 16) ^ int(item.value_norm, 16)).bit_count()
            if distance > 8:
                continue
            excerpt = f"Perceptual image hash distance {distance}"
        else:
            try:
                text, _ = await get_text(session, case.id, evidence.id, settings)
            except (AppError, FileNotFoundError):
                continue
            normalized = normalize(text)
            positions = [normalized.find(normalize(v)) for v in item.variants]
            positions = [p for p in positions if p >= 0]
            if not positions:
                continue
            # Return a bounded excerpt. Original character spans remain in extraction rows.
            excerpt = normalized[max(0, min(positions) - 150) : min(positions) + 1000]
        hits.append(
            Hit(
                evidence.id,
                evidence.code,
                excerpt,
                evidence.source_class,
                f"evidence://{case.id}/{evidence.id}",
                evidence.sha256,
                family_of(evidence),
                image_distance=distance,
            )
        )
    return hits


def arguments(source: str, item) -> dict:
    if source in {"chain_lookup", "sanctions_check"}:
        chain = (
            "ETH"
            if item.value.startswith("0x")
            else "TRON"
            if item.value.startswith("T")
            else "BTC"
        )
        return {"address": item.value, "chain": chain}
    if source == "keyserver_lookup":
        return {"fingerprint": item.value_norm}
    if source in {"onion_lookup", "onion_fetch"}:
        return {"url": "http://" + item.value_norm + "/"}
    return {"query": item.value}


async def collect(session, case, item, source, ctx) -> list[Hit]:
    if source == "evidence":
        return await local_hits(session, case, item, ctx.settings)
    result = await invoke(ctx, source, arguments(source, item))
    if not result.ok:
        error = result.error or {}
        raise ToolError(
            error.get("code", "UNAVAILABLE"),
            error.get("message", "Monitoring source unavailable"),
            error.get("detail"),
        )
    data = result.data or {}
    if not data.get("evidence_id") or data.get("quarantined"):
        return []
    evidence = await get_evidence(session, case.id, data["evidence_id"])
    if evidence.status not in {"READY", "PARTIAL"}:
        return []
    locator = (
        FieldCipher(ctx.settings.field_key).decrypt(evidence.locator_enc, str(case.id))
        if evidence.locator_enc
        else f"evidence://{case.id}/{evidence.id}"
    )
    from urllib.parse import urlsplit

    family = hashlib.sha256((urlsplit(locator).hostname or "unknown").encode()).hexdigest()
    return [
        Hit(
            evidence.id,
            evidence.code,
            data.get("excerpt", ""),
            evidence.source_class,
            locator,
            evidence.sha256,
            family,
        )
    ]
