import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv
from seed_synthetic_case import ROOT, login


def evaluate(args):
    load_dotenv(ROOT / ".env")
    seed = json.loads(args.seed_result.read_text(encoding="utf-8"))
    document = yaml.safe_load(args.questions.read_text(encoding="utf-8"))
    questions = document if isinstance(document, list) else document["questions"]
    results = []
    with httpx.Client(base_url=args.api, timeout=60) as client:
        login(
            client,
            "analyst.demo",
            os.environ["DARKNETRA_DEMO_ANALYST_PASSWORD"],
            os.getenv("DARKNETRA_WEB_ORIGIN", "http://localhost:3000"),
        )
        for item in questions:
            if item.get("lane") != "evidence":
                continue
            expected = {seed["files"].get(name, name) for name in item["expected_codes"]}
            response = client.post(
                f"/api/v1/cases/{seed['case_id']}/search", json={"query": item["question"], "k": 5}
            )
            response.raise_for_status()
            found = {hit["evidence"]["code"] for hit in response.json()["hits"]}
            recall = len(expected & found) / len(expected) if expected else 1
            results.append(
                {
                    "question": item["question"],
                    "expected": sorted(expected),
                    "found": sorted(found),
                    "recall_at_5": recall,
                }
            )
    score = sum(row["recall_at_5"] for row in results) / len(results) if results else 0
    out = ROOT / "backend/evals/out" / f"retrieval-{datetime.now(UTC):%Y%m%d%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"source_class": "SYNTHETIC", "recall_at_5": score, "questions": results}, indent=2
        ),
        encoding="utf-8",
    )
    print(f"Recall@5: {score:.3f} ({len(results)} questions)")
    return 0 if score >= 0.9 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seed-result", type=Path, default=ROOT / "data/synthetic/out/seed_result.json"
    )
    parser.add_argument("--questions", type=Path, default=ROOT / "backend/evals/questions.yaml")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    raise SystemExit(evaluate(parser.parse_args()))
