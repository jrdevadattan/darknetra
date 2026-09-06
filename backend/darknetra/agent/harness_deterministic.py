"""Explicit local quotation mode; no simulated model inference."""

import json
from collections.abc import AsyncIterator
from typing import Any

from darknetra.tools.contracts import ToolContext
from darknetra.tools.invoke import invoke


class DeterministicHarness:
    async def run(
        self,
        ctx: ToolContext,
        prompt: str,
        *,
        goal: str | None = None,
        history: list[dict[str, Any]] | None = None,
        budget: float = 2.0,
    ) -> AsyncIterator[dict[str, Any]]:
        found = await invoke(ctx, "search_evidence", {"query": prompt, "k": 5, "mode": "lexical"})
        entities = await invoke(ctx, "list_entities", {"limit": 200})
        claims = []
        for code in ctx.context_evidence_codes[:20]:
            read = await invoke(
                ctx,
                "read_evidence",
                {"evidence_code": code, "start_line": 1, "end_line": 3, "max_chars": 1200},
            )
            if read.ok and read.data and read.data["text"].strip():
                quotation = read.data["text"].replace("\n", " ").strip()
                claims.append(
                    {
                        "text": f"“{quotation}” [{code} L1]",
                        "evidence_codes": [code],
                        "kind": "observed",
                    }
                )
        requested_types: set[str] = set()
        if any(term in prompt.casefold() for term in ("wallet", "address", "bitcoin", "btc")):
            requested_types.update({"BTC_ADDRESS", "ETH_ADDRESS", "TRON_ADDRESS", "XMR_ADDRESS"})
        if any(term in prompt.casefold() for term in ("pgp", "fingerprint", "public key")):
            requested_types.add("PGP_FINGERPRINT")
        if entities.ok and entities.data and requested_types:
            for entity in entities.data.get("entities", []):
                if entity["type"] not in requested_types:
                    continue
                spans = entity.get("evidence_spans", [])
                if not spans:
                    continue
                citations = " ".join(
                    f"[{item['evidence']['code']} L{item['span'].get('line') or 1}]"
                    for item in spans
                )
                text = f"{entity['type']}: {entity['display']} {citations}"
                claims.append(
                    {
                        "text": text,
                        "evidence_codes": sorted({item["evidence"]["code"] for item in spans}),
                        "kind": "observed",
                    }
                )
        if not claims and found.ok and found.data:
            seen: set[str] = set()
            for hit in found.data.get("hits", []):
                code = hit["evidence"]["code"]
                if code in seen:
                    continue
                seen.add(code)
                line = hit.get("span", {}).get("line") or 1
                read = await invoke(
                    ctx,
                    "read_evidence",
                    {
                        "evidence_code": code,
                        "start_line": line,
                        "end_line": line + 2,
                        "max_chars": 1200,
                    },
                )
                if read.ok and read.data and read.data["text"].strip():
                    quotation = read.data["text"].replace("\n", " ").strip()
                    text = f"“{quotation}” [{code} L{line}]"
                    claims.append({"text": text, "evidence_codes": [code], "kind": "observed"})
        text = "\n".join(c["text"] for c in claims) if claims else "Insufficient evidence."
        if claims:
            text += "\n```claims\n" + json.dumps(claims) + "\n```"
        yield {"type": "assistant", "text": text}
        yield {"type": "usage", "cost_usd": 0, "tokens_in": 0, "tokens_out": 0}
