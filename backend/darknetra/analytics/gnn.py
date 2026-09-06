"""Optional fixed research model adapter; no synthetic predictions or guessed thresholds."""

import importlib.util
from pathlib import Path

from sqlalchemy import select

from darknetra.analytics.models import LedgerAddress, LedgerEdge, LedgerNode
from darknetra.api.v1.schemas.analytics import GnnAssessment


class GnnPredictor:
    def __init__(self, model_path=None, predictor=None):
        self.model_path = (
            Path(model_path)
            if model_path
            else Path(__file__).resolve().parents[3] / "models/gnn/predict.py"
        )
        self.predictor = predictor
        self.available = predictor is not None or (
            self.model_path.is_file()
            and importlib.util.find_spec("torch") is not None
            and importlib.util.find_spec("torch_geometric") is not None
        )
        self.unavailable_reason = None if self.available else "model unavailable"

    async def assess(self, session, case_id, address):
        mapping = await session.scalar(
            select(LedgerAddress).where(
                LedgerAddress.case_id == case_id, LedgerAddress.address == address
            )
        )
        if mapping is None:
            self.unavailable_reason = "address not in ledger"
            return None
        if not self.available:
            self.unavailable_reason = "model unavailable"
            return None
        node_ids, frontier = {mapping.node_index}, {mapping.node_index}
        from sqlalchemy import or_

        for _ in range(2):
            edges = list(
                await session.scalars(
                    select(LedgerEdge)
                    .where(
                        LedgerEdge.case_id == case_id,
                        or_(LedgerEdge.src.in_(frontier), LedgerEdge.dst.in_(frontier)),
                    )
                    .order_by(LedgerEdge.src, LedgerEdge.dst)
                    .limit(20001)
                )
            )
            adjacent = {v for e in edges for v in (e.src, e.dst)} - node_ids
            frontier = set(sorted(adjacent)[: max(0, 2000 - len(node_ids))])
            node_ids.update(frontier)
        nodes = list(
            await session.scalars(
                select(LedgerNode)
                .where(LedgerNode.case_id == case_id, LedgerNode.node_index.in_(node_ids))
                .order_by(LedgerNode.node_index)
            )
        )
        if not nodes or len(nodes) != len(node_ids) or any(len(n.features) != 102 for n in nodes):
            self.unavailable_reason = "ledger features unavailable"
            return None
        edges = list(
            await session.scalars(
                select(LedgerEdge).where(
                    LedgerEdge.case_id == case_id,
                    LedgerEdge.src.in_(node_ids),
                    LedgerEdge.dst.in_(node_ids),
                )
            )
        )
        positions = {n.node_index: i for i, n in enumerate(nodes)}
        try:
            predictor = self.predictor
            if predictor is None:
                spec = importlib.util.spec_from_file_location(
                    "darknetra_fixed_gnn", self.model_path
                )
                if spec is None or spec.loader is None:
                    self.unavailable_reason = "model unavailable"
                    return None
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                predictor = module.predict
            result = predictor(
                [n.features for n in nodes],
                [[positions[e.src] for e in edges], [positions[e.dst] for e in edges]],
                positions[mapping.node_index],
            )
            validated = GnnAssessment.model_validate(result)
            if (
                validated.n_nodes != len(nodes)
                or not 0 <= validated.illicit_probability <= 1
                or not 0 <= validated.licit_probability <= 1
                or not 0 < validated.threshold < 1
            ):
                raise ValueError("Invalid model result")
            self.unavailable_reason = None
            return validated
        except (ImportError, OSError, ValueError, TypeError, AttributeError, RuntimeError):
            self.unavailable_reason = "model unavailable or incompatible artefacts"
            return None
