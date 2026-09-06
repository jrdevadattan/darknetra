"""Seed exclusively through authenticated public APIs; never upload ground truth."""

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def login(client, username, password, origin):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": origin},
    )
    response.raise_for_status()
    client.headers.update({"Origin": origin, "X-CSRF-Token": client.cookies["darknetra_csrf"]})
    return response.json()


def seed(args):
    load_dotenv(ROOT / ".env")
    admin_password = os.environ["DARKNETRA_ADMIN_PASSWORD"]
    analyst_password = os.environ["DARKNETRA_DEMO_ANALYST_PASSWORD"]
    origin = os.getenv("DARKNETRA_WEB_ORIGIN", "http://localhost:3000")
    bundle = args.bundle
    if not (bundle / "manifest.json").exists():
        sys.path.insert(0, str(ROOT / "data/synthetic"))
        from generator import generate

        generate(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source_class") != "SYNTHETIC":
        raise ValueError("Seed manifest must be SYNTHETIC")
    for item in manifest["files"]:
        path = (bundle / item["filename"]).resolve()
        if (
            not path.is_relative_to(bundle.resolve())
            or path.name in {"ground_truth.json", "manifest.json"}
            or item.get("source_class") != "SYNTHETIC"
        ):
            raise ValueError("Invalid manifest member")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Synthetic manifest hash mismatch")
    with httpx.Client(base_url=args.api, timeout=180) as client:
        admin = login(client, "administrator", admin_password, origin)
        if admin.get("must_change_password"):
            raise RuntimeError(
                "Run backend/scripts/manage.py bootstrap to complete administrator setup before seeding"
            )
        response = client.get("/api/v1/users", params={"limit": 200})
        response.raise_for_status()
        users = response.json().get("items", [])
        existing = next((u for u in users if u["username"] == "analyst.demo"), None)
        temporary_password = secrets.token_urlsafe(32) if not existing else None
        if not existing:
            response = client.post(
                "/api/v1/users",
                json={
                    "username": "analyst.demo",
                    "display_name": "SYNTHETIC Demo Analyst",
                    "global_role": "INVESTIGATOR",
                    "password": temporary_password,
                },
            )
            response.raise_for_status()
        client.cookies.clear()
        login(client, "analyst.demo", temporary_password or analyst_password, origin)
        if temporary_password:
            response = client.post(
                "/api/v1/auth/change-password",
                json={"current_password": temporary_password, "new_password": analyst_password},
            )
            response.raise_for_status()
            client.cookies.clear()
            login(client, "analyst.demo", analyst_password, origin)
        response = client.get("/api/v1/cases", params={"limit": 200})
        response.raise_for_status()
        previous = [
            case
            for case in response.json().get("items", [])
            if case.get("demo")
            and case["title"] == "SYN-CHD-001 synthetic demo"
            and case["status"] != "ARCHIVED"
        ]
        if previous and args.if_missing:
            case = previous[0]
            evidence_response = client.get(
                f"/api/v1/cases/{case['id']}/evidence", params={"limit": 200}
            )
            evidence_response.raise_for_status()
            evidence_by_hash = {e["sha256"]: e for e in evidence_response.json()["items"]}
        else:
            if args.reset:
                for case in previous:
                    if case["status"] == "OPEN":
                        client.post(
                            f"/api/v1/cases/{case['id']}/close",
                            json={"reason": "SYNTHETIC demo reset"},
                        ).raise_for_status()
                    client.post(
                        f"/api/v1/cases/{case['id']}/archive",
                        json={"reason": "SYNTHETIC demo reset"},
                    ).raise_for_status()
            response = client.post(
                "/api/v1/cases",
                json={
                    "title": "SYN-CHD-001 synthetic demo",
                    "demo": True,
                    "scope_notes": "SYNTHETIC training evidence only",
                },
            )
            response.raise_for_status()
            case = response.json()
            evidence_by_hash = {}
        result = {
            "source_class": "SYNTHETIC",
            "case_id": case["id"],
            "case_code": case["code"],
            "files": {},
        }
        for item in manifest["files"]:
            name = item["filename"]
            path = (bundle / name).resolve()
            evidence = evidence_by_hash.get(item["sha256"])
            if evidence is None:
                upload_data = {"source_class": "SYNTHETIC"}
                if item.get("source_family"):
                    upload_data["source_family"] = item["source_family"]
                with path.open("rb") as stream:
                    response = client.post(
                        f"/api/v1/cases/{case['id']}/evidence",
                        files={"files": (path.name, stream)},
                        data=upload_data,
                    )
                response.raise_for_status()
                payload = response.json()
                if payload["errors"]:
                    raise RuntimeError("Synthetic upload failed")
                evidence = payload["results"][0]["evidence"]
            deadline = time.monotonic() + 180
            while evidence["status"] == "PROCESSING":
                if time.monotonic() >= deadline:
                    raise RuntimeError("Synthetic processing timed out")
                time.sleep(0.2)
                poll = client.get(f"/api/v1/cases/{case['id']}/evidence/{evidence['id']}")
                poll.raise_for_status()
                evidence = poll.json()
            if evidence["status"] == "FAILED":
                raise RuntimeError("Synthetic evidence processing failed")
            result["files"][name] = evidence["code"]
        output = ROOT / "data/synthetic/out/seed_result.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"SYNTHETIC case {result['case_code']}: {len(result['files'])} evidence entries")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--if-missing", action="store_true")
    group.add_argument("--reset", action="store_true")
    parser.add_argument("--bundle", type=Path, default=ROOT / "data/synthetic/out/SYN-CHD-001")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    seed(parser.parse_args())
