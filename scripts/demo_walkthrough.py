"""Exercise the synthetic investigation over HTTP, including durable SSE and exports."""

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def require(response):
    response.raise_for_status()
    return response.json()


def walk(api: str) -> None:
    load_dotenv(ROOT / ".env")
    seed = json.loads(
        (ROOT / "data/synthetic/out/seed_result.json").read_text(encoding="utf-8")
    )
    base = f"/api/v1/cases/{seed['case_id']}"
    transcript = {
        "source_class": "SYNTHETIC",
        "case_code": seed["case_code"],
        "steps": [],
    }
    start = time.monotonic()

    def checkpoint(name: str, **facts):
        transcript["steps"].append(
            {
                "step": name,
                "elapsed_seconds": round(time.monotonic() - start, 2),
                **facts,
            }
        )
        print(name + ": passed", flush=True)

    with httpx.Client(
        base_url=api,
        timeout=120,
        headers={"Origin": os.getenv("DARKNETRA_WEB_ORIGIN", "http://localhost:3000")},
    ) as client:
        user = require(
            client.post(
                "/api/v1/auth/login",
                json={
                    "username": "analyst.demo",
                    "password": os.environ["DARKNETRA_DEMO_ANALYST_PASSWORD"],
                },
            )
        )
        assert not user["must_change_password"]
        client.headers["X-CSRF-Token"] = client.cookies["darknetra_csrf"]
        evidence = require(client.get(base + "/evidence", params={"limit": 200}))[
            "items"
        ]
        assert len([e for e in evidence if e["source_class"] == "SYNTHETIC"]) >= 14
        assert all(e["status"] != "PROCESSING" for e in evidence)
        checkpoint("Synthetic evidence inventory", count=len(evidence))

        search = require(
            client.post(base + "/search", json={"query": "SYNTHETIC_ALIAS_A", "k": 5})
        )
        assert search["hits"]
        checkpoint("Case retrieval", mode=search["mode_used"])
        thread = require(
            client.post(base + "/threads", json={"title": "SYNTHETIC walkthrough"})
        )
        assert thread["harness"] == "DETERMINISTIC", (
            "This walkthrough requires the explicit local deterministic mode"
        )
        run = require(
            client.post(
                base + f"/threads/{thread['id']}/messages",
                json={"content": "SYNTHETIC_ALIAS_A"},
            )
        )
        events, event_name, event_id, data = [], None, None, []
        with client.stream(
            "GET", base + f"/threads/{thread['id']}/runs/{run['run_id']}/events"
        ) as stream:
            stream.raise_for_status()
            for line in stream.iter_lines():
                if not line:
                    if event_name and data:
                        events.append(
                            {
                                "type": event_name,
                                "id": event_id,
                                "data": json.loads("\n".join(data)),
                            }
                        )
                    event_name, event_id, data = None, None, []
                elif line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("id:"):
                    event_id = line[3:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].strip())
        assert events and any(e["type"] == "run.finished" for e in events), events
        messages = require(client.get(base + f"/threads/{thread['id']}/messages"))[
            "items"
        ]
        answers = [m for m in messages if m["role"] == "ASSISTANT"]
        assert answers and answers[-1]["claims"] and answers[-1]["verification"]["ok"]
        checkpoint(
            "Cited answer and persisted SSE",
            events=len(events),
            claims=len(answers[-1]["claims"]),
        )

        require(client.post(base + "/analytics/correlate", json={}))
        deadline = time.monotonic() + 45
        while True:
            candidates = require(
                client.get(base + "/analytics/links", params={"limit": 200})
            )["items"]
            planted = next(
                (
                    candidate
                    for candidate in candidates
                    if {
                        candidate["subject_a"]["value"].casefold(),
                        candidate["subject_b"]["value"].casefold(),
                    }
                    == {"synthetic_alias_a", "synthetic_alias_a_chat"}
                ),
                None,
            )
            if planted:
                break
            if time.monotonic() > deadline:
                raise AssertionError("Planted alias pair was not correlated")
            time.sleep(0.25)
        assert planted["band"] == "STRONG", planted
        if planted["status"] != "ACCEPTED":
            require(
                client.post(
                    base + "/decisions",
                    headers={"If-Match": str(planted["version"])},
                    json={
                        "target_type": "LINK",
                        "target_id": planted["id"],
                        "decision": "ACCEPT",
                        "rationale": "SYNTHETIC walkthrough review: planted public PGP fingerprint and contact match.",
                        "supersede": planted["decision"] is not None,
                    },
                )
            )
        graph = require(client.get(base + "/graph"))
        assert any(
            edge["status"] == "CONFIRMED"
            and edge["type"] == "ANALYST_CONFIRMED_RELATED"
            for edge in graph["edges"]
        )
        checkpoint(
            "Synthetic review decision and confirmed graph", band=planted["band"]
        )

        truth = json.loads(
            (ROOT / "data/synthetic/out/SYN-CHD-001/ground_truth.json").read_text()
        )
        wallet = require(
            client.post(
                base + "/wallets/assess",
                json={"address": truth["wallets"]["W1"], "chain": "btc", "live": False},
            )
        )
        assert wallet["gnn"] is not None or wallet["gnn_unavailable_reason"]
        assert wallet["sanctions"] is not None or (wallet["live_summary"] or {}).get(
            "sanctions_unavailable_reason"
        )
        checkpoint(
            "Wallet assessment availability",
            gnn_available=wallet["gnn"] is not None,
            sanctions_available=wallet["sanctions"] is not None,
        )

        lists = require(client.get(base + "/watchlists"))["items"]
        watchlist = next(
            (w for w in lists if w["name"] == "SYNTHETIC walkthrough"), None
        )
        if watchlist is None:
            watchlist = require(
                client.post(
                    base + "/watchlists", json={"name": "SYNTHETIC walkthrough"}
                )
            )
        items = require(client.get(base + f"/watchlists/{watchlist['id']}/items"))[
            "items"
        ]
        item = next(
            (item for item in items if item["value"] == truth["wallets"]["W1"]), None
        )
        if item is None:
            item = require(
                client.post(
                    base + f"/watchlists/{watchlist['id']}/items",
                    json={
                        "type": "WALLET",
                        "value": truth["wallets"]["W1"],
                        "sources": ["evidence"],
                    },
                )
            )
        require(
            client.post(base + f"/watchlists/{watchlist['id']}/items/{item['id']}/run")
        )
        alerts = require(client.get(base + "/alerts", params={"item_id": item["id"]}))[
            "items"
        ]
        assert alerts
        alert = next((alert for alert in alerts if alert["status"] == "OPEN"), None)
        if alert:
            escalated = require(
                client.post(
                    base + f"/alerts/{alert['id']}/escalate",
                    json={
                        "rationale": "SYNTHETIC fixture monitoring review for the walkthrough."
                    },
                )
            )
            assert escalated["finding"]
        checkpoint("Local evidence monitoring and alert review", alerts=len(alerts))

        job = require(
            client.post(
                base + "/reports",
                json={"redact": True, "narrative": False, "include_appendix": True},
            )
        )
        deadline = time.monotonic() + 120
        while True:
            report = require(client.get(base + f"/reports/{job['report_id']}"))
            if report["status"] in {"DONE", "ERROR"}:
                break
            if time.monotonic() > deadline:
                raise AssertionError("Report generation timed out")
            time.sleep(0.3)
        assert report["status"] == "DONE", report
        download = client.get(
            base + f"/reports/{report['id']}/download", params={"format": "md"}
        )
        download.raise_for_status()
        assert "SYNTHETIC" in download.text and "Evidence appendix" in download.text
        for claim in answers[-1]["claims"]:
            for code in claim["evidence_codes"]:
                assert code in download.text
        checkpoint(
            "Versioned report and evidence appendix",
            report_id=report["id"],
            download_sha256=hashlib.sha256(download.content).hexdigest(),
        )
    output = (
        ROOT
        / "backend/evals/out"
        / f"walkthrough-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
    print("SYNTHETIC walkthrough complete: " + str(output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    walk(parser.parse_args().api)
