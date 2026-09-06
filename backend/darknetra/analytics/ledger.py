"""Validated append-only ledger import. Original CSV files become evidence."""

import csv
import io
import math

from sqlalchemy import select

from darknetra.analytics.models import LedgerAddress, LedgerEdge, LedgerNode
from darknetra.analytics.wallets import validate_address
from darknetra.api.v1.schemas.cases import LedgerImportResult
from darknetra.audit.service import digest, record
from darknetra.cases.models import Case
from darknetra.errors import Conflict, TooLarge, Validation
from darknetra.evidence.service import ingest_bytes

MAX_FILE_BYTES = 10 * 1024 * 1024


def csv_rows(data: bytes, required, limit):
    if len(data) > MAX_FILE_BYTES:
        raise TooLarge("Ledger file exceeds ten MiB")
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        if (
            not reader.fieldnames
            or not set(required) <= set(reader.fieldnames)
            or len(reader.fieldnames) != len(set(reader.fieldnames))
        ):
            raise Validation("Ledger CSV is missing required unique columns")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise Validation("Ledger CSV has inconsistent columns")
            rows.append(row)
            if len(rows) > limit:
                raise TooLarge("Ledger row limit exceeded")
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise Validation("Ledger file must be valid UTF-8 CSV") from exc


def parse_ledger(nodes, edges, address_map):
    feature_names = [f"f_{i}" for i in range(102)]
    node_rows = csv_rows(nodes, ["node_index", "timestep", "label", *feature_names], 100000)
    edge_rows = csv_rows(edges, ["src", "dst"], 200000)
    address_rows = csv_rows(address_map, ["address", "chain", "node_index"], 100000)
    parsed_nodes, parsed_edges, parsed_addresses = {}, {}, {}
    source_classes = {
        r.get("source_class", "UPLOAD") for r in [*node_rows, *edge_rows, *address_rows]
    }
    if source_classes - {"SYNTHETIC", "UPLOAD", "SEIZED"} or (
        "SYNTHETIC" in source_classes and len(source_classes) > 1
    ):
        raise Validation("Ledger source classes must be explicit and consistently synthetic")
    source_class = "SYNTHETIC" if source_classes == {"SYNTHETIC"} else "UPLOAD"
    try:
        for row in node_rows:
            index = int(row["node_index"])
            features = [float(row[name]) for name in feature_names]
            if index < 0 or index in parsed_nodes or any(not math.isfinite(v) for v in features):
                raise ValueError("invalid node")
            txid = row.get("txid") or (
                f"SYNTHETIC_NODE_{index}" if source_class == "SYNTHETIC" else None
            )
            if not txid or len(txid) > 256:
                raise ValueError("transaction identifier required")
            parsed_nodes[index] = dict(
                node_index=index,
                txid=txid,
                timestep=int(row["timestep"]),
                label=int(row["label"]),
                features=features,
            )
        for row in edge_rows:
            src, dst = int(row["src"]), int(row["dst"])
            if src not in parsed_nodes or dst not in parsed_nodes:
                raise ValueError("edge references missing node")
            parsed_edges[src, dst] = dict(src=src, dst=dst)
        for row in address_rows:
            index = int(row["node_index"])
            if index not in parsed_nodes:
                raise ValueError("address references missing node")
            address, chain = validate_address(row["address"], row["chain"].casefold())
            if address in parsed_addresses:
                raise ValueError("duplicate address")
            tag = row.get("tag") or None
            if tag not in {None, "unknown", "vendor_controlled", "shared_service", "escrow"}:
                raise ValueError("unsupported tag")
            parsed_addresses[address] = dict(
                address=address, chain=chain, node_index=index, tag=tag
            )
    except (ValueError, OverflowError) as exc:
        raise Validation("Ledger contains invalid, duplicate, or dangling data") from exc
    if not parsed_nodes:
        raise Validation("Ledger must contain at least one node")
    return parsed_nodes, parsed_edges, parsed_addresses, source_class


async def import_ledger(
    session, *, case, actor, nodes, edges, address_map, settings, request_id=None
):
    parsed_nodes, parsed_edges, parsed_addresses, source_class = parse_ledger(
        nodes, edges, address_map
    )
    locked = await session.scalar(select(Case).where(Case.id == case.id).with_for_update())
    if locked.status != "OPEN":
        raise Conflict("Case is not open")
    for model, parsed, key_fields in (
        (LedgerNode, parsed_nodes, ("node_index",)),
        (LedgerEdge, parsed_edges, ("src", "dst")),
        (LedgerAddress, parsed_addresses, ("address",)),
    ):
        current = {
            tuple(getattr(r, name) for name in key_fields): r
            for r in await session.scalars(select(model).where(model.case_id == case.id))
        }
        for values in parsed.values():
            key = tuple(values[name] for name in key_fields)
            old = current.get(key)
            if old:
                if any(getattr(old, field) != value for field, value in values.items()):
                    raise Conflict("Ledger rows cannot overwrite previously imported data")
            else:
                session.add(model(case_id=case.id, **values))
        await session.flush()
    evidence_ids = []
    for name, data in (
        ("nodes.csv", nodes),
        ("edges.csv", edges),
        ("address_map.csv", address_map),
    ):
        result = await ingest_bytes(
            session,
            case=case,
            actor=actor,
            data=data,
            filename=name,
            settings=settings,
            source_class=source_class,
            meta={"ledger_import": True, "synthetic": source_class == "SYNTHETIC"},
        )
        evidence_ids.append(str(result.evidence.id))
    result = LedgerImportResult(
        nodes=len(parsed_nodes), edges=len(parsed_edges), addresses=len(parsed_addresses)
    )
    await record(
        session,
        actor=actor,
        case_id=case.id,
        action="ledger.import",
        target_type="case",
        target_id=case.id,
        request_id=request_id,
        detail={**result.model_dump(), "evidence_ids": evidence_ids},
        result_hash=digest(result.model_dump()),
    )
    return result
