#!/usr/bin/env python3
"""Guarded GitHub Models implementation runner for DARKNETRA Plans 03 and 04.

This script is intended for the one-shot GitHub Actions completion workflow. It
uses test-first batches, path allow-lists, immutable test hashes, bounded model
context, repeated verification, and commits each green checkpoint to the
`testing-codex` branch. It never sends repository secrets, runtime keys, object
store bytes, or user data to a model; only source-controlled code and synthetic
fixtures are included.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
MAX_CONTEXT_CHARS = 360_000
MAX_LOG_CHARS = 60_000
MODEL_ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODEL_FALLBACKS = (
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o",
)

EXCLUDED_PARTS = {
    ".git",
    ".next",
    ".pnpm-store",
    ".snapshot",
    ".turbo",
    ".venv",
    "node_modules",
    "playwright-report",
    "test-results",
    "__pycache__",
}

TEST_PREFIXES = (
    "apps/api/tests/",
    "apps/web/e2e/",
    "evaluation/",
    "datasets/synthetic/",
)
TEST_SUFFIXES = (
    ".test.ts",
    ".test.tsx",
    ".spec.ts",
    ".spec.tsx",
)

PROTECTED_PATHS = {
    "docs/superpowers/plans/2026-08-17-03-evidence-vault-ingestion.md",
    "docs/superpowers/plans/2026-08-17-04-extraction-indicators.md",
    "scripts/plan_completion_agent.py",
}


@dataclass(frozen=True, slots=True)
class Batch:
    name: str
    title: str
    plan_path: str
    task_numbers: tuple[int, ...]
    context_patterns: tuple[str, ...]
    red_commands: tuple[str, ...]
    green_commands: tuple[str, ...]
    commit_message: str
    expected_new_feature: bool = True


BATCHES = (
    Batch(
        name="plan03-gap-audit",
        title="Plan 03 Evidence Vault completion audit and gap closure",
        plan_path="docs/superpowers/plans/2026-08-17-03-evidence-vault-ingestion.md",
        task_numbers=tuple(range(1, 14)),
        context_patterns=(
            "apps/api/darknetra_api/**/*.py",
            "apps/api/tests/**/*.py",
            "apps/api/alembic/**/*.py",
            "apps/web/src/features/evidence/**/*",
            "apps/web/src/app/**/evidence/**/*",
            "apps/web/e2e/**/*evidence*",
            "docker-compose*.yml",
            "apps/api/pyproject.toml",
            "apps/web/package.json",
            "README.md",
            "docs/architecture/evidence*.md",
            "docs/verification/plan03*.md",
        ),
        red_commands=(
            "uv run pytest -q apps/api/tests",
            "pnpm --filter @darknetra/web test -- --run",
        ),
        green_commands=(
            "uv run ruff check .",
            "uv run pytest -q",
            "pnpm --filter @darknetra/web lint",
            "pnpm --filter @darknetra/web typecheck",
            "pnpm --filter @darknetra/web test -- --run",
            "pnpm --filter @darknetra/web build",
            "docker compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null",
        ),
        commit_message="feat: close remaining Evidence Vault plan gaps",
        expected_new_feature=False,
    ),
    Batch(
        name="plan04-foundation",
        title="Plan 04 tasks 1-3: entity schema, lossless normalization, scripts and transliteration",
        plan_path="docs/superpowers/plans/2026-08-17-04-extraction-indicators.md",
        task_numbers=(1, 2, 3),
        context_patterns=(
            "apps/api/darknetra_api/models/**/*.py",
            "apps/api/darknetra_api/schemas/**/*.py",
            "apps/api/darknetra_api/nlp/**/*.py",
            "apps/api/darknetra_api/db/**/*.py",
            "apps/api/alembic/**/*.py",
            "apps/api/tests/**/*.py",
            "apps/api/pyproject.toml",
            "models/manifests/**/*",
        ),
        red_commands=("uv run pytest -q apps/api/tests",),
        green_commands=(
            "uv run ruff check .",
            "uv run pytest -q",
            "uv run alembic -c apps/api/alembic.ini upgrade head",
        ),
        commit_message="feat: add multilingual entity extraction foundation",
    ),
    Batch(
        name="plan04-indicators",
        title="Plan 04 tasks 4-6: deterministic commercial, OpenPGP and crypto indicators",
        plan_path="docs/superpowers/plans/2026-08-17-04-extraction-indicators.md",
        task_numbers=(4, 5, 6),
        context_patterns=(
            "apps/api/darknetra_api/extractors/**/*.py",
            "apps/api/darknetra_api/validators/**/*.py",
            "apps/api/darknetra_api/nlp/**/*.py",
            "apps/api/darknetra_api/models/**/*.py",
            "apps/api/tests/**/*.py",
            "apps/api/pyproject.toml",
            "infrastructure/docker/**/*",
        ),
        red_commands=("uv run pytest -q apps/api/tests",),
        green_commands=(
            "uv run ruff check .",
            "uv run pytest -q",
        ),
        commit_message="feat: validate deterministic investigation indicators",
    ),
    Batch(
        name="plan04-pipeline",
        title="Plan 04 tasks 7-9: taxonomy, local semantic adapter, persistence and novel terms",
        plan_path="docs/superpowers/plans/2026-08-17-04-extraction-indicators.md",
        task_numbers=(7, 8, 9),
        context_patterns=(
            "apps/api/darknetra_api/nlp/**/*.py",
            "apps/api/darknetra_api/extractors/**/*.py",
            "apps/api/darknetra_api/validators/**/*.py",
            "apps/api/darknetra_api/services/**/*.py",
            "apps/api/darknetra_api/jobs/**/*.py",
            "apps/api/darknetra_api/models/**/*.py",
            "apps/api/tests/**/*.py",
            "models/manifests/**/*",
            "apps/api/pyproject.toml",
        ),
        red_commands=("uv run pytest -q apps/api/tests",),
        green_commands=(
            "uv run ruff check .",
            "uv run pytest -q",
        ),
        commit_message="feat: persist versioned evidence linked extraction",
    ),
    Batch(
        name="plan04-product",
        title="Plan 04 tasks 10-12: Entities API, investigator UI and evaluation harness",
        plan_path="docs/superpowers/plans/2026-08-17-04-extraction-indicators.md",
        task_numbers=(10, 11, 12),
        context_patterns=(
            "apps/api/darknetra_api/routes/**/*.py",
            "apps/api/darknetra_api/repositories/**/*.py",
            "apps/api/darknetra_api/services/**/*.py",
            "apps/api/darknetra_api/schemas/**/*.py",
            "apps/api/darknetra_api/models/**/*.py",
            "apps/api/tests/**/*.py",
            "apps/web/src/features/**/*",
            "apps/web/src/app/**/entities/**/*",
            "apps/web/src/lib/**/*",
            "apps/web/e2e/**/*",
            "apps/web/package.json",
            "evaluation/**/*",
            "datasets/synthetic/**/*",
        ),
        red_commands=(
            "uv run pytest -q apps/api/tests",
            "pnpm --filter @darknetra/web test -- --run",
        ),
        green_commands=(
            "uv run ruff check .",
            "uv run pytest -q",
            "pnpm --filter @darknetra/web lint",
            "pnpm --filter @darknetra/web typecheck",
            "pnpm --filter @darknetra/web test -- --run",
            "pnpm --filter @darknetra/web build",
        ),
        commit_message="feat: add evidence linked entity review experience",
    ),
    Batch(
        name="plan04-final-docs",
        title="Plan 04 task 13 and final README/documentation alignment",
        plan_path="docs/superpowers/plans/2026-08-17-04-extraction-indicators.md",
        task_numbers=(13,),
        context_patterns=(
            "README.md",
            ".env.example",
            "docker-compose*.yml",
            "Makefile",
            "docs/architecture/**/*.md",
            "docs/verification/**/*.md",
            "evaluation/**/*",
            "models/manifests/**/*",
            "apps/api/pyproject.toml",
            "apps/web/package.json",
        ),
        red_commands=(),
        green_commands=(
            "uv run ruff check .",
            "uv run pytest -q",
            "pnpm --filter @darknetra/web lint",
            "pnpm --filter @darknetra/web typecheck",
            "pnpm --filter @darknetra/web test -- --run",
            "pnpm --filter @darknetra/web build",
            "docker compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null",
        ),
        commit_message="docs: document verified Evidence Vault and extraction milestones",
        expected_new_feature=False,
    ),
)


def log(message: str) -> None:
    print(message, flush=True)


def run(
    command: str,
    *,
    check: bool = False,
    timeout: int = 1800,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    log(f"$ {command}")
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    completed = subprocess.run(
        ["bash", "-lc", command],
        cwd=ROOT,
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = completed.stdout
    if len(output) > MAX_LOG_CHARS:
        output = output[-MAX_LOG_CHARS:]
    print(output, flush=True)
    if check and completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {command}\n{output}")
    return completed.returncode, output


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def safe_relative(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"unsafe model path: {path!r}")
    if candidate.parts[0] == ".git" or is_excluded(candidate):
        raise ValueError(f"excluded model path: {path!r}")
    return candidate


def is_test_path(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    return normalized.startswith(TEST_PREFIXES) or normalized.endswith(TEST_SUFFIXES)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in ROOT.rglob("*"):
        if path.is_file() and not is_excluded(path.relative_to(ROOT)):
            relative = path.relative_to(ROOT).as_posix()
            if is_test_path(relative):
                result[relative] = file_sha256(path)
    return result


def task_text(plan_path: Path, task_numbers: Iterable[int]) -> str:
    text = plan_path.read_text(encoding="utf-8")
    sections: list[str] = []
    for number in task_numbers:
        pattern = re.compile(
            rf"(?ms)^### Task {number}:.*?(?=^---\s*$|^### Task \d+:|^## Plan \d+ Definition of Done|\Z)"
        )
        match = pattern.search(text)
        if not match:
            raise RuntimeError(f"Task {number} not found in {plan_path}")
        sections.append(match.group(0).strip())
    definition_match = re.search(
        r"(?ms)^## Plan \d+ Definition of Done.*?(?=^## Plan \d+ handoff contract|\Z)",
        text,
    )
    if definition_match:
        sections.append(definition_match.group(0).strip())
    return "\n\n---\n\n".join(sections)


def matched_paths(patterns: Iterable[str]) -> list[Path]:
    found: set[Path] = set()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if is_excluded(relative):
            continue
        rel = relative.as_posix()
        if any(fnmatch.fnmatch(rel, pattern) for pattern in patterns):
            found.add(path)
    return sorted(found, key=lambda p: p.relative_to(ROOT).as_posix())


def repository_tree(limit: int = 1200) -> str:
    entries: list[str] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if is_excluded(relative) or not path.is_file():
            continue
        entries.append(relative.as_posix())
    entries.sort()
    if len(entries) > limit:
        entries = entries[:limit] + [f"... {len(entries) - limit} additional files omitted"]
    return "\n".join(entries)


def context_bundle(patterns: Iterable[str], *, extra_paths: Iterable[str] = ()) -> str:
    candidates = matched_paths(patterns)
    for relative in extra_paths:
        path = ROOT / relative
        if path.exists() and path.is_file() and path not in candidates:
            candidates.append(path)
    candidates.sort(key=lambda p: p.relative_to(ROOT).as_posix())

    chunks = ["CURRENT REPOSITORY TREE\n" + repository_tree()]
    used = len(chunks[0])
    for path in candidates:
        relative = path.relative_to(ROOT).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if len(content) > 24_000:
            content = content[:24_000] + "\n... file truncated for model context ...\n"
        block = f"\n\n===== FILE: {relative} =====\n{content}"
        if used + len(block) > MAX_CONTEXT_CHARS:
            continue
        chunks.append(block)
        used += len(block)
    return "".join(chunks)


def strip_code_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        stripped = stripped[first : last + 1]
    return stripped


def model_request(system: str, user: str, *, attempts: int = 5) -> dict[str, Any]:
    token = os.environ.get("GH_MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GitHub Models token is unavailable")

    errors: list[str] = []
    for attempt in range(attempts):
        model = MODEL_FALLBACKS[attempt % len(MODEL_FALLBACKS)]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": 30000,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            MODEL_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                raw = response.read().decode("utf-8")
            result = json.loads(raw)
            content = result["choices"][0]["message"]["content"]
            decoded = json.loads(strip_code_fence(content))
            if not isinstance(decoded, dict):
                raise TypeError("model response is not a JSON object")
            decoded["_model"] = model
            return decoded
        except Exception as exc:  # network/model errors are retried with bounded backoff
            detail = f"{model}: {type(exc).__name__}: {str(exc)[:500]}"
            errors.append(detail)
            log(detail)
            time.sleep(min(20, 2 ** attempt))
    raise RuntimeError("GitHub Models request failed: " + " | ".join(errors))


SYSTEM_PROMPT = """You are a senior security-focused engineer completing DARKNETRA, an evidence-first authorized investigation platform. You modify a real monorepo. Return one JSON object only, never markdown. The JSON schema is {\"summary\": string, \"red_required\": boolean, \"files\": [{\"path\": string, \"content\": string}], \"delete\": [string]}. Every file entry contains the complete UTF-8 file content, not a patch. Keep scope strictly to the requested batch. Preserve the existing architecture and style. PostgreSQL is authoritative; Redis is transient; originals are immutable; the browser never receives object-store credentials or paths. Never add live darknet access, credential bypass, seller contact, purchases, decryption bypass, offensive tooling, secret keys, real criminal identifiers, or operational procurement instructions. Tests and datasets must be harmless, synthetic, and fictional. Do not weaken security tests. Do not invent successful metrics. Do not claim guilt or identity from indicators. All model-derived entities require source spans. Formal protocol validation outranks inference. Runtime model/download failure must be explicit and fail safely. No network model downloads occur in request handlers or workers."""


def apply_model_files(
    response: dict[str, Any],
    *,
    phase: str,
    locked_tests: dict[str, str] | None = None,
) -> list[str]:
    changed: list[str] = []
    files = response.get("files", [])
    deletes = response.get("delete", [])
    if not isinstance(files, list) or not isinstance(deletes, list):
        raise TypeError("model files/delete fields must be arrays")

    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("content"), str):
            raise TypeError("invalid model file entry")
        relative = safe_relative(item["path"]).as_posix()
        if relative in PROTECTED_PATHS or relative.startswith(".github/workflows/"):
            raise ValueError(f"model attempted to modify protected path: {relative}")
        if phase == "tests" and not is_test_path(relative):
            raise ValueError(f"test phase attempted production change: {relative}")
        if phase != "tests" and is_test_path(relative):
            if locked_tests and locked_tests.get(relative) == hashlib.sha256(item["content"].encode("utf-8")).hexdigest():
                continue
            raise ValueError(f"implementation phase attempted test change: {relative}")
        destination = ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(item["content"], encoding="utf-8")
        changed.append(relative)

    for raw in deletes:
        if not isinstance(raw, str):
            raise TypeError("delete path must be a string")
        relative = safe_relative(raw).as_posix()
        if relative in PROTECTED_PATHS or relative.startswith(".github/workflows/"):
            raise ValueError(f"model attempted to delete protected path: {relative}")
        if phase == "tests" or is_test_path(relative):
            raise ValueError(f"model attempted forbidden deletion: {relative}")
        target = ROOT / relative
        if target.is_file() or target.is_symlink():
            target.unlink()
            changed.append(relative)
        elif target.is_dir():
            shutil.rmtree(target)
            changed.append(relative)
    return changed


def assert_test_hashes(expected: dict[str, str]) -> None:
    observed = test_hashes()
    modified = [path for path, digest in expected.items() if observed.get(path) != digest]
    deleted = [path for path in expected if path not in observed]
    if modified or deleted:
        raise RuntimeError(f"locked tests changed after RED: modified={modified}, deleted={deleted}")


def dependency_refresh() -> None:
    status = run("git diff --name-only", check=True)[1]
    changed = set(status.splitlines())
    if any(path.endswith("pyproject.toml") for path in changed):
        run("uv lock", check=True, timeout=1200)
        run("uv sync --all-packages --dev --frozen", check=True, timeout=1200)
    if any(path.endswith("package.json") for path in changed):
        run("pnpm install --lockfile-only", check=True, timeout=1200)
        run("pnpm install --frozen-lockfile", check=True, timeout=1200)


def commands_result(commands: Iterable[str]) -> tuple[bool, str]:
    logs: list[str] = []
    all_green = True
    for command in commands:
        code, output = run(command, timeout=2400)
        logs.append(f"\n### {command}\nexit={code}\n{output}")
        if code != 0:
            all_green = False
            break
    combined = "".join(logs)
    return all_green, combined[-MAX_LOG_CHARS:]


def git_commit_and_push(message: str) -> str:
    run("git add -A", check=True)
    code, output = run("git diff --cached --quiet")
    if code == 0:
        sha = run("git rev-parse HEAD", check=True)[1].strip()
        log(f"No changes for checkpoint {message!r}; current {sha}")
        return sha
    run(f"git commit -m {json.dumps(message)}", check=True)
    for attempt in range(4):
        code, output = run("git push origin HEAD:testing-codex")
        if code == 0:
            return run("git rev-parse HEAD", check=True)[1].strip()
        log(f"push attempt {attempt + 1} failed; rebasing")
        run("git pull --rebase origin testing-codex", check=True)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"unable to push checkpoint: {output}")


def execute_batch(batch: Batch) -> None:
    marker = ROOT / "docs" / "verification" / f"{batch.name}.md"
    if marker.exists() and "Outcome: success" in marker.read_text(encoding="utf-8"):
        log(f"Skipping already verified batch {batch.name}")
        return

    log(f"\n{'=' * 88}\nSTART {batch.title}\n{'=' * 88}")
    plan = task_text(ROOT / batch.plan_path, batch.task_numbers)
    context = context_bundle(
        batch.context_patterns,
        extra_paths=(batch.plan_path, "pyproject.toml", "pnpm-workspace.yaml", "docker-compose.yml", ".env.example"),
    )

    test_prompt = f"""PHASE: RED / TEST DESIGN

BATCH: {batch.title}

PLAN CONTRACT:
{plan}

CURRENT TREE AND RELEVANT FILES:
{context}

Audit the existing implementation against every requested behavior. Add only missing, high-value tests or synthetic evaluation fixtures. Do not modify production code, dependency files, migrations, documentation, or workflows. Tests must assert public behavior, exact provenance, authorization, anti-enumeration, fail-closed security, idempotency and edge cases. Use the project's existing test conventions. If the current implementation and tests already completely satisfy this batch, return no files and set red_required=false; otherwise set red_required=true. Never create tests that require live darknet access, real criminal data, internet downloads, private keys or purchases."""
    tests_response = model_request(SYSTEM_PROMPT, test_prompt)
    test_changes = apply_model_files(tests_response, phase="tests")
    red_required = bool(tests_response.get("red_required", batch.expected_new_feature))

    red_log = "No new tests were required."
    if test_changes:
        green_before, red_log = commands_result(batch.red_commands or ("uv run pytest -q",))
        if red_required and green_before:
            strengthen_prompt = f"""The first RED tests unexpectedly passed, so they did not expose a missing behavior. Review the plan contract and current code again. Add or replace only tests/fixtures for genuinely missing required behavior. Do not modify production. Existing new test files may be replaced. Return red_required=true only when at least one test should fail for the missing implementation.

PLAN:
{plan}

TEST RUN OUTPUT:
{red_log}

CURRENT CONTEXT:
{context_bundle(batch.context_patterns, extra_paths=(batch.plan_path,))}"""
            response = model_request(SYSTEM_PROMPT, strengthen_prompt)
            apply_model_files(response, phase="tests")
            red_required = bool(response.get("red_required", True))
            green_before, red_log = commands_result(batch.red_commands or ("uv run pytest -q",))
        if red_required and green_before:
            raise RuntimeError(f"Batch {batch.name} did not produce an honest RED failure")
        if not red_required and not green_before:
            raise RuntimeError(f"Batch {batch.name} claimed no missing behavior but tests failed: {red_log}")
    elif red_required:
        # A missing feature without a test is not accepted; ask once more.
        retry_prompt = test_prompt + "\n\nYou returned no tests while claiming RED is required. Return concrete test files now."
        response = model_request(SYSTEM_PROMPT, retry_prompt)
        test_changes = apply_model_files(response, phase="tests")
        if not test_changes:
            raise RuntimeError(f"Batch {batch.name} could not produce test-first coverage")
        green_before, red_log = commands_result(batch.red_commands or ("uv run pytest -q",))
        if green_before:
            raise RuntimeError(f"Batch {batch.name} tests passed before implementation")

    locked = test_hashes()
    implementation_context = context_bundle(
        batch.context_patterns,
        extra_paths=(batch.plan_path, "apps/api/pyproject.toml", "apps/web/package.json", "README.md"),
    )
    implementation_prompt = f"""PHASE: GREEN / IMPLEMENTATION

BATCH: {batch.title}

PLAN CONTRACT:
{plan}

TEST-FIRST RESULT:
{red_log}

CURRENT TREE AND RELEVANT FILES (including locked tests):
{implementation_context}

Implement every requirement in this batch with the smallest coherent production change. You may create or replace production source, schemas, migrations, dependency manifests, model manifests, architecture documentation, synthetic non-test resources and README sections. Do not modify, delete, skip or weaken any test/evaluation fixture. Reuse existing authentication, case policy, encryption, audit, custody, object-store and Celery boundaries. Preserve backward compatibility unless the plan explicitly requires a migration. Generate deterministic migration revisions with correct down_revision. Use offline/fail-safe adapters when optional NLP models are absent. Return complete file contents."""
    implementation = model_request(SYSTEM_PROMPT, implementation_prompt)
    apply_model_files(implementation, phase="implementation", locked_tests=locked)
    assert_test_hashes(locked)
    dependency_refresh()

    green, green_log = commands_result(batch.green_commands)
    repair_attempt = 0
    while not green and repair_attempt < 4:
        repair_attempt += 1
        repair_context = context_bundle(
            batch.context_patterns,
            extra_paths=(batch.plan_path, "apps/api/pyproject.toml", "apps/web/package.json"),
        )
        repair_prompt = f"""PHASE: ROOT-CAUSE REPAIR {repair_attempt}

BATCH: {batch.title}

The locked test suite or build failed after implementation. Diagnose the root cause from the complete error below, compare with working patterns in the repository, and return only production/dependency/migration fixes. Do not modify tests, evaluation labels, plans or workflows. Do not mask failures, loosen assertions, skip tests, add blanket ignores or replace real behavior with mocks.

PLAN CONTRACT:
{plan}

FAILURE OUTPUT:
{green_log}

CURRENT RELEVANT FILES:
{repair_context}"""
        repair = model_request(SYSTEM_PROMPT, repair_prompt)
        apply_model_files(repair, phase="repair", locked_tests=locked)
        assert_test_hashes(locked)
        dependency_refresh()
        green, green_log = commands_result(batch.green_commands)

    if not green:
        diagnostic = ROOT / "docs" / "verification" / f"{batch.name}-failure.md"
        diagnostic.parent.mkdir(parents=True, exist_ok=True)
        diagnostic.write_text(
            f"# {batch.title} failure\n\n```text\n{green_log[-40_000:]}\n```\n",
            encoding="utf-8",
        )
        git_commit_and_push(f"docs: record {batch.name} verification failure [skip ci]")
        raise RuntimeError(f"Batch {batch.name} remained red after bounded repairs")

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        f"# {batch.title}\n\n"
        "- Outcome: success\n"
        f"- Verified source: `{run('git rev-parse HEAD', check=True)[1].strip()}`\n"
        f"- Model used for implementation: `{implementation.get('_model', 'unknown')}`\n"
        f"- Test-first files added or updated: {len(test_changes)}\n"
        f"- Repair attempts: {repair_attempt}\n\n"
        "## Verification commands\n\n"
        + "\n".join(f"- `{command}` — success" for command in batch.green_commands)
        + "\n",
        encoding="utf-8",
    )
    git_commit_and_push(batch.commit_message)


def final_security_review() -> None:
    plan03 = (ROOT / "docs/superpowers/plans/2026-08-17-03-evidence-vault-ingestion.md").read_text(encoding="utf-8")
    plan04 = (ROOT / "docs/superpowers/plans/2026-08-17-04-extraction-indicators.md").read_text(encoding="utf-8")
    context = context_bundle(
        (
            "apps/api/darknetra_api/**/*.py",
            "apps/api/tests/**/*.py",
            "apps/web/src/features/evidence/**/*",
            "apps/web/src/features/entities/**/*",
            "apps/web/src/app/**/evidence/**/*",
            "apps/web/src/app/**/entities/**/*",
            "evaluation/**/*",
            "README.md",
            "docker-compose*.yml",
            "apps/api/pyproject.toml",
            "apps/web/package.json",
        )
    )
    prompt = f"""PHASE: INDEPENDENT FINAL SECURITY AND SPEC REVIEW

Review the current implementation against BOTH complete plan definitions of done. Focus on authorization, unsafe parsing/execution, archive traversal/bombs, HTML active content, immutable hashes, object-key exposure, cross-case access, audit/custody transactionality, worker idempotency, exact source spans, Unicode offset mapping, protocol validation, hallucinated entities, model-offline behavior, sensitive value redaction, test honesty and README truthfulness.

PLAN 03:
{plan03}

PLAN 04:
{plan04}

CURRENT IMPLEMENTATION:
{context}

Return production fixes only when a concrete issue exists. Do not modify tests/plans/workflows. If no concrete issue exists, return empty files/delete arrays and explain the review in summary."""
    locked = test_hashes()
    review = model_request(SYSTEM_PROMPT, prompt)
    apply_model_files(review, phase="review", locked_tests=locked)
    assert_test_hashes(locked)
    dependency_refresh()
    if review.get("files") or review.get("delete"):
        green, output = commands_result(
            (
                "uv run ruff check .",
                "uv run pytest -q",
                "pnpm --filter @darknetra/web lint",
                "pnpm --filter @darknetra/web typecheck",
                "pnpm --filter @darknetra/web test -- --run",
                "pnpm --filter @darknetra/web build",
                "docker compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null",
            )
        )
        if not green:
            raise RuntimeError(f"Final review fixes broke verification:\n{output}")
        git_commit_and_push("fix: address final Evidence Vault and extraction review")
    review_doc = ROOT / "docs/verification/plan03-plan04-security-review.md"
    review_doc.write_text(
        "# Plans 03 and 04 independent security review\n\n"
        f"- Model: `{review.get('_model', 'unknown')}`\n"
        f"- Production files changed: {len(review.get('files', []))}\n"
        f"- Summary: {str(review.get('summary', '')).strip()}\n",
        encoding="utf-8",
    )
    git_commit_and_push("docs: record final Evidence Vault and extraction review [skip ci]")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", action="append", help="Run only the named batch; may repeat")
    parser.add_argument("--skip-review", action="store_true")
    args = parser.parse_args()

    os.chdir(ROOT)
    selected = set(args.batch or [batch.name for batch in BATCHES])
    unknown = selected - {batch.name for batch in BATCHES}
    if unknown:
        raise SystemExit(f"unknown batches: {sorted(unknown)}")

    for batch in BATCHES:
        if batch.name in selected:
            execute_batch(batch)
    if not args.skip_review and selected == {batch.name for batch in BATCHES}:
        final_security_review()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
