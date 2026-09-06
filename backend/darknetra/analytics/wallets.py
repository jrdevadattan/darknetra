"""Case-local wallet assessment with explicit absent-provider results."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from darknetra.analytics.gnn import GnnPredictor
from darknetra.analytics.models import LedgerAddress, WalletAssessment
from darknetra.analytics.sanctions import OfacList
from darknetra.audit.service import digest, record
from darknetra.cases.models import Case
from darknetra.errors import Conflict, NetworkRequired, NotFound, Unavailable, Validation
from darknetra.extract.validators import find_crypto


def validate_address(address, chain=None):
    address = address.strip()
    candidates = [c for c in find_crypto(address) if c.raw == address]
    if len(candidates) != 1 or (not candidates[0].valid and candidates[0].type != "XMR_ADDRESS"):
        raise Validation("Address failed chain validation")
    candidate = candidates[0]
    detected = {
        "BTC_ADDRESS": "btc",
        "ETH_ADDRESS": "eth",
        "TRON_ADDRESS": "tron",
        "XMR_ADDRESS": "xmr",
    }[candidate.type]
    if chain and chain != detected:
        raise Validation("Address does not match the requested chain")
    return candidate.normalized["value"], detected


async def assess_wallet(session, case, actor, request, settings):
    locked = await session.scalar(select(Case).where(Case.id == case.id).with_for_update())
    if locked is None:
        raise NotFound("Resource not found")
    if locked.status != "OPEN":
        raise Conflict("Case is not open")
    address, chain = validate_address(request.address, request.chain)
    if request.live:
        if settings.offline_mode:
            raise NetworkRequired("Live wallet assessment requires network access")
        raise Unavailable("Live chain assessment requires a configured capture-gate adapter")
    predictor, sanctions = GnnPredictor(), OfacList()
    gnn = None if chain == "xmr" else await predictor.assess(session, case.id, address)
    sanctions_result = sanctions.check(address)
    mapping = await session.scalar(
        select(LedgerAddress).where(
            LedgerAddress.case_id == case.id, LedgerAddress.address == address
        )
    )
    latest = await session.scalar(
        select(func.max(WalletAssessment.version)).where(
            WalletAssessment.case_id == case.id, WalletAssessment.address == address
        )
    )
    limitations = {"live_status": "not_requested"}
    if sanctions_result is None:
        limitations["sanctions_unavailable_reason"] = sanctions.unavailable_reason
    if chain == "xmr":
        limitations["traceability_reason"] = (
            "Monero public chain tracing is unavailable; address checksum unverified"
        )
    row = WalletAssessment(
        case_id=case.id,
        address=address,
        chain=chain,
        gnn=gnn.model_dump(mode="json") if gnn else None,
        gnn_unavailable_reason="Monero ledger assessment unsupported"
        if chain == "xmr"
        else predictor.unavailable_reason,
        sanctions=sanctions_result.model_dump(mode="json") if sanctions_result else None,
        live_summary=limitations,
        tags=[mapping.tag] if mapping and mapping.tag else [],
        traceable=chain != "xmr",
        version=(latest or 0) + 1,
        assessed_at=datetime.now(UTC),
        requested_by_kind="USER" if actor.kind in {"USER", "TOKEN"} else "SYSTEM",
        requested_by_id=actor.user_id or actor.id,
    )
    session.add(row)
    await session.flush()
    await record(
        session,
        actor=actor,
        case_id=case.id,
        action="wallet.assess",
        target_type="wallet_assessment",
        target_id=row.id,
        detail={
            "chain": chain,
            "gnn_available": gnn is not None,
            "sanctions_available": sanctions_result is not None,
        },
        result_hash=digest(
            {"id": row.id, "gnn": row.gnn, "sanctions": row.sanctions, "limitations": limitations}
        ),
    )
    return row
