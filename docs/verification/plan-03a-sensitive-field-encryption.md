# Plan 03a sensitive-field encryption verification

## Final fix verification

### Tested tree identity

- Verification window: `2026-08-25T05:14:54Z` through `2026-08-25T05:27:32Z`
- Base commit: `8b3e25f20db1c81f371191e76c727b8d286f82ac`
- Tested implementation commit: `e1c13e88d9ebe46c953c63358f33de78fb1db4ca`
- Patch byte length: `71288`
- Patch SHA-256: `f81b48f3d2eda4d1dd67a9f11223fbf7f7f225ab33d5d3bbd982d6cd40bd4579`
- Branch: `codex/complete-roadmap`

The tested-tree identity is the base commit plus the binary Git patch for every tracked final-fix
change except this verification record. Excluding this record removes the hash self-reference. No
other path is excluded. Run this command from the final tree to reproduce the byte length and hash:

```bash
uv run python - <<'PY'
import hashlib
import subprocess

base = "8b3e25f20db1c81f371191e76c727b8d286f82ac"
record = "docs/verification/plan-03a-sensitive-field-encryption.md"
patch = subprocess.check_output(
    [
        "git",
        "diff",
        "--binary",
        "--no-ext-diff",
        base,
        "--",
        ".",
        f":(exclude){record}",
    ]
)
print(len(patch))
print(hashlib.sha256(patch).hexdigest())
PY
```

Expected output:

```text
71288
f81b48f3d2eda4d1dd67a9f11223fbf7f7f225ab33d5d3bbd982d6cd40bd4579
```

### TDD evidence

The first focused run after adding the collision, key-version, key-source, and mapping-isolation
tests produced `9 failed, 47 passed in 10.46s`. The failures were:

- colon-shifted AAD tuples authenticated as the same context;
- the Hypothesis colon-boundary property found the same collision;
- NUL-shifted blind-index tuples produced the same HMAC;
- the Hypothesis NUL-boundary property found the same collision;
- dotted resource-type and field-name tuples revealed plaintext;
- decoded-equivalent legacy and JSON `v1` keys were rejected as conflicting;
- the missing encryption-key error named only the legacy source;
- a changing source mapping passed validation and stored different key material; and
- settings accepted an invalid active key version.

After the production changes, the focused crypto, config, encrypted-field, version, keyring, and
reveal suite reported `81 passed in 2.06s`.

### Local commands and observed results

```powershell
uv run pytest -q apps/api/tests/unit/test_sensitive_field_encryption.py apps/api/tests/unit/test_sensitive_field_config.py apps/api/tests/unit/test_encrypted_fields.py apps/api/tests/unit/test_sensitive_field_key_versions.py apps/api/tests/unit/test_sensitive_field_keyring.py apps/api/tests/unit/test_sensitive_value_reveal.py
uv run pytest -q -m 'not integration'
uv run ruff check .
```

Observed results:

- Focused tests: exit 0, `81 passed in 2.06s`.
- Non-integration suite: exit 0, `114 passed, 26 deselected, 1 warning in 4.92s`.
- Ruff: exit 0, `All checks passed!`.
- Final pre-commit rerun: exit 0, `114 passed, 26 deselected, 1 warning in 5.12s`; Ruff again
  reported `All checks passed!`.
- The warning is the existing Starlette deprecation for using `httpx` through
  `starlette.testclient`.

The E2E Compose configuration was run once without a JWT key and once with a runtime-generated
32-byte key in a temporary env file. The absent-key command failed as required by the Compose
`${DARKNETRA_JWT_SIGNING_KEY_B64:?...}` expression. The runtime env configuration parsed, the API
environment contained a non-empty key, and the temporary file was removed. The verification script
printed:

```text
COMPOSE_MISSING_KEY=failed_closed
COMPOSE_RUNTIME_ENV=valid
COMPOSE_RUNTIME_ENV_CLEANUP=removed
```

PyYAML parsed `.github/workflows/plan02-task13.yml`, and Git Bash `bash -n` accepted all 14 workflow
run blocks. The tracked env, documentation, workflow, and Compose scan checked 62 text files. It
found zero 32-byte Base64 key candidates and zero literal JWT, field-key, keyring, or blind-index
assignments. The Plan 02 Task 13 workflow contains no `GITHUB_ENV` reference. It creates a masked
mode-600 file under `RUNNER_TEMP`, checks the file before each Compose use, passes it with
`--env-file`, and removes it during cleanup. A fresh Gitleaks binary was not available on the local
host, so this final-fix section makes no fresh Gitleaks claim. A final repeat widened the tracked
scope to 67 paths and again found zero Base64 key candidates and zero literal secret assignments;
PyYAML and all 14 Bash blocks passed again.

The changed Markdown structural check verified blank lines after headings, balanced code fences,
and balanced bold markers outside inline code. `git diff --check` exited 0.

### Isolated Linux full suite

The full suite ran on GCP VM `unique-ops-phase1` in Compose project `plan03affc7f3a1b4` under
`/tmp/plan03a-finalfix-c7f3a1b4`. The base Compose configuration parsed with no host ports. The run
built the API image, started only its isolated PostgreSQL service, created separate main and E2E
databases, applied both migrations, and ran Linux Ruff plus full pytest in the built API image.

Observed results:

- Linux Ruff: exit 0, `All checks passed!`.
- Full pytest: exit 0, `140 passed, 1 warning in 68.35s`.
- The warning was the same existing Starlette deprecation.
- Cleanup removed the temporary container, network, volume, API image tag, archive, and `/tmp`
  directory.
- All nine containers in Compose project `unique-operations` remained unchanged. `docker compose
  ls` listed that protected project as `running(9)` after cleanup.

The first VM attempt built the unique API image but stopped before PostgreSQL startup because the
script queried `docker compose images` before an API container existed. Its cleanup removed the
temporary Compose resources and directory and confirmed the protected containers were unchanged.
The exact remaining unique image tag was removed, the script was corrected to inspect the known
project image tag, and the complete run above then passed and cleaned every artifact.

### Security and plan checks

- AES-GCM AAD and blind-index HMAC input use separate domains, format version 1, component counts,
  and eight-byte unsigned big-endian length prefixes.
- Regression and property tests cover colon, NUL, and dotted tuple ambiguity.
- One shared `v[1-9][0-9]{0,62}` validator covers settings, JSON/direct keyrings, crypto,
  decryption, pack, and unpack.
- Legacy and JSON `v1` sources compare decoded bytes. Missing-key errors name JSON and legacy
  sources. Mapping snapshot and repr redaction behavior have direct tests.
- Plan 03 now requires verified Plan 03a, complete protected-value envelopes and HMAC blind
  indexes, pack/unpack, audited reveal, read-only adapters, and startup/readiness crypto validation.
- Blind-index rotation requires a complete offline rebuild or a versioned dual-write/backfill/
  dual-read migration with matching backup handling.
- No GitHub Actions run supplied final-fix evidence. This record makes no GitHub Actions success
  claim.

## Prior Plan 03a verification

- Verification window: `2026-08-25T04:36:33Z` through `2026-08-25T04:38:47Z`
- Tested code commit: `e199e06b6d0712b620922834809ff4cb76a02de9`
- Branch: `codex/complete-roadmap`
- Tested Task 5 changes: the architecture and verification documents, runtime JWT interpolation
  in `docker-compose.e2e.yml`, and runtime JWT generation in
  `.github/workflows/plan02-task13.yml`
- Local host: Windows `10.0.26200`, uv `0.11.20`, Python `3.14.5`
- Linux host: GCP VM `unique-ops-phase1` in `asia-south1-a`, Ubuntu kernel
  `6.17.0-1022-gcp`, x86_64, Python `3.12.3`
- Container toolchain: Docker `29.1.3`, Compose `2.40.3`, Python `3.12.14`, uv `0.12.4`
- Secret scanner: Gitleaks `8.30.1`, image digest
  `sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f`

The commit SHA identifies the reviewed Plan 03a implementation. Task 5 documentation and the
runtime-key cleanup were uncommitted working-tree changes during the run. They do not change the
Python application or tests.

## Runtime keys and isolation

The Linux run generated four independent 32-byte values with this command, called once for the JWT
key, twice for the `v1` and `v2` field keys, and once for the blind-index key:

```bash
python3 -c 'import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode("ascii"))'
```

The shell built `DARKNETRA_FIELD_KEYRING_B64_JSON` from the generated `v1` and `v2` values and set
`DARKNETRA_FIELD_ACTIVE_KEY_VERSION=v2`. It generated the isolated PostgreSQL password with
`secrets.token_hex(24)`. No command printed a key or wrote one to the repository.

Run this script to construct the runtime values:

```bash
runtime_key() {
  python3 -c 'import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode("ascii"))'
}

export DARKNETRA_POSTGRES_PASSWORD
export DARKNETRA_JWT_SIGNING_KEY_B64
export DARKNETRA_FIELD_KEY_V1_B64
export DARKNETRA_FIELD_KEYRING_B64_JSON
export DARKNETRA_FIELD_BLIND_INDEX_KEY_B64
DARKNETRA_POSTGRES_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
DARKNETRA_JWT_SIGNING_KEY_B64="$(runtime_key)"
DARKNETRA_FIELD_KEY_V1_B64="$(runtime_key)"
field_key_v2_b64="$(runtime_key)"
DARKNETRA_FIELD_BLIND_INDEX_KEY_B64="$(runtime_key)"
DARKNETRA_FIELD_KEYRING_B64_JSON="$(python3 -c 'import json,os,sys; print(json.dumps({"v1":os.environ["DARKNETRA_FIELD_KEY_V1_B64"],"v2":sys.argv[1]},separators=(",",":")))' "$field_key_v2_b64")"
unset field_key_v2_b64
```

The run used temporary directory `/tmp/plan03a-task5-20260825-0415-a91f7c2d` and Compose project
`plan03at5a91f7c2d`. The temporary Compose override only mapped the runtime field-key variables into
the API container. It declared no ports. The base Compose file ran without the development or E2E
port overlays.

Create the override without key values:

```bash
work_dir=/tmp/plan03a-task5-20260825-0415-a91f7c2d
override="$work_dir/compose.plan03a.yml"
python3 - "$override" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    """services:
  api:
    environment:
      DARKNETRA_FIELD_KEY_V1_B64: ${DARKNETRA_FIELD_KEY_V1_B64:?runtime v1 field key required}
      DARKNETRA_FIELD_KEYRING_B64_JSON: ${DARKNETRA_FIELD_KEYRING_B64_JSON:?runtime field keyring required}
      DARKNETRA_FIELD_BLIND_INDEX_KEY_B64: ${DARKNETRA_FIELD_BLIND_INDEX_KEY_B64:?runtime blind-index key required}
      DARKNETRA_FIELD_ACTIVE_KEY_VERSION: v2
""",
    encoding="utf-8",
)
PY
```

Before the run, `/opt/unique-operations` owned one Compose project with nine healthy containers.
Its published ports were 80, 443, 5432, and 9000. After verification, the temporary containers,
volume, network, API image, repository clone, bundle, logs, and directory were removed. The same
nine protected containers remained healthy with the same ports, and `docker compose ls` listed only
`unique-operations`.

## Commands and observed results

The local preflight ran:

```text
uv run ruff check .
```

Result: exit 0, `All checks passed!` at `2026-08-25T04:14:13Z`.

The Linux run used this command array:

```bash
compose=(sudo -n -E docker compose -p plan03at5a91f7c2d -f docker-compose.yml -f /tmp/plan03a-task5-20260825-0415-a91f7c2d/compose.plan03a.yml)
"${compose[@]}" config --quiet
"${compose[@]}" config --format json | python3 -c 'import json,sys; data=json.load(sys.stdin); published={name:svc.get("ports",[]) for name,svc in data["services"].items() if svc.get("ports")}; assert not published,published; print("COMPOSE_CONFIG=no host ports")'
"${compose[@]}" build api
"${compose[@]}" up -d --wait postgres api
"${compose[@]}" exec -T api python -c 'import json,urllib.request; live=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health/live",timeout=5)); ready=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health/ready",timeout=5)); assert live["status"]=="ok"; assert ready["status"]=="ready"'
"${compose[@]}" exec -T --workdir /app/apps/api api /app/.venv/bin/python -c 'from darknetra_api.config import Settings; crypto=Settings().require_sensitive_field_crypto(); assert crypto.active_key_version=="v2"; assert crypto.key_versions==frozenset({"v1","v2"}); value=crypto.encrypt("runtime smoke value",purpose="source.locator",resource_id="smoke-resource"); assert crypto.decrypt(value,purpose="source.locator",resource_id="smoke-resource")=="runtime smoke value"; assert len(crypto.blind_index("runtime smoke value",purpose="source.locator"))==64'
```

Results:

- Compose configuration: exit 0; parsed configuration contained no host ports.
- API image build: exit 0. Compose warned that buildx was absent and used its available Docker
  builder.
- API and PostgreSQL startup: both containers became healthy.
- Internal API probe: live returned `status=ok`; readiness returned `status=ready`.
- Runtime crypto probe: settings loaded `v1` and `v2`, selected `v2`, completed a source-locator
  round trip, and produced a 64-character blind index.

The test runner attached to the temporary Compose network and used the built API image. It mounted
the isolated repository at `/work`. The main and E2E PostgreSQL databases had separate names in the
same temporary PostgreSQL container.

```bash
"${compose[@]}" exec -T postgres createdb -U darknetra darknetra_e2e_test
network_name="$(sudo -n docker network ls --filter "label=com.docker.compose.project=plan03at5a91f7c2d" --format '{{.Name}}' | head -n 1)"
api_image="$("${compose[@]}" images -q api)"
test -n "$network_name"
test -n "$api_image"
repo="$work_dir/repo"
database_url="postgresql+psycopg://darknetra:${DARKNETRA_POSTGRES_PASSWORD}@postgres:5432/darknetra"
e2e_database_url="postgresql+psycopg://darknetra:${DARKNETRA_POSTGRES_PASSWORD}@postgres:5432/darknetra_e2e_test"

sudo -n docker run --rm --user 0:0 \
  --network "$network_name" \
  --volume "$repo:/work" \
  --workdir /work \
  --env DARKNETRA_DATABASE_URL="$database_url" \
  --env DARKNETRA_E2E_DATABASE_URL="$e2e_database_url" \
  --env DARKNETRA_JWT_SIGNING_KEY_B64="$DARKNETRA_JWT_SIGNING_KEY_B64" \
  "$api_image" \
  sh -lc '
    set -eu
    uv sync --frozen --all-packages --dev
    uv run alembic -c apps/api/alembic.ini upgrade head
    DARKNETRA_DATABASE_URL="$DARKNETRA_E2E_DATABASE_URL" uv run alembic -c apps/api/alembic.ini upgrade head
    uv run ruff check .
    uv run pytest -q apps/api/tests/integration/test_sensitive_value_reveal_integration.py
    uv run pytest -q \
      apps/api/tests/unit/test_passwords.py \
      apps/api/tests/unit/test_tokens.py \
      apps/api/tests/unit/test_policy.py \
      apps/api/tests/integration/test_bootstrap_admin.py \
      apps/api/tests/integration/test_auth_flow.py \
      apps/api/tests/integration/test_auth_cors.py \
      apps/api/tests/integration/test_case_lifecycle.py \
      apps/api/tests/integration/test_cross_case_authorization.py \
      apps/api/tests/integration/test_case_memberships.py
    uv run pytest -q
  '
```

Observed results:

| Check | Result |
| --- | --- |
| Linux Ruff | exit 0, `All checks passed!` |
| PostgreSQL sensitive reveal integration | exit 0, `1 passed in 8.18s` |
| Authentication and case regressions | exit 0, `30 passed in 22.31s` |
| Full pytest suite | exit 0, `130 passed, 1 warning in 39.75s` |

The warning is Starlette's existing deprecation warning for using `httpx` through
`starlette.testclient`. It did not fail a test.

The secret gate ran:

```bash
docker run --rm -v "$PWD:/repo:ro" zricethezav/gitleaks:latest \
  detect --source=/repo --no-git --redact --exit-code=1 --no-banner
git diff --check
```

Run the custom scan with this script:

```bash
python3 - <<'PY'
import re
import subprocess
from pathlib import Path

paths = subprocess.check_output(
    ["git", "ls-files", ".env*", "*.env", "docs/**"],
    text=True,
).splitlines()
architecture = Path("docs/architecture/sensitive-field-encryption.md")
if architecture.exists() and architecture.as_posix() not in paths:
    paths.append(architecture.as_posix())

candidate = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{43}=(?![A-Za-z0-9+/=])")
assignment = re.compile(
    r"^\s*(DARKNETRA_(?:JWT_SIGNING_KEY_B64|FIELD_KEY_V1_B64|FIELD_KEYRING_B64_JSON|FIELD_BLIND_INDEX_KEY_B64))\s*[:=]\s*(.*?)\s*$"
)
runtime_expression = re.compile(r'''^["']?\$(?:\(|\{)''')
hits = []
literal_assignments = []
for name in paths:
    path = Path(name)
    if not path.is_file():
        continue
    if path.suffix.lower() not in {".md", ".txt", ".env", ".example"} and ".env" not in path.name:
        continue
    text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        if candidate.search(line):
            hits.append(f"{name}:{number}")
        match = assignment.match(line)
        if match and match.group(2) and not runtime_expression.match(match.group(2)):
            literal_assignments.append(f"{name}:{number}")
assert not hits, f"32-byte Base64-looking values in env/docs: {hits}"
assert not literal_assignments, f"literal secret assignments in env/docs: {literal_assignments}"
print(f"ENV_DOC_KEY_SCAN={len(paths)} files, zero Base64 key candidates, zero literal secret assignments")
PY
```

Observed results:

- Gitleaks scanned about 1.69 MB and reported `no leaks found`.
- The tracked env/document scan checked 33 paths and found zero 32-byte Base64 candidates and zero
  literal assignments for the JWT, field-key, keyring, or blind-index variables.
- `git diff --check` exited 0.

I ran these VM cleanup commands:

```bash
cd /tmp/plan03a-task5-20260825-0415-a91f7c2d/repo
sudo -n docker compose -p plan03at5a91f7c2d -f docker-compose.yml down --volumes --remove-orphans
sudo -n docker image rm plan03at5a91f7c2d-api:latest
cd /tmp
test "$(realpath /tmp/plan03a-task5-20260825-0415-a91f7c2d)" = /tmp/plan03a-task5-20260825-0415-a91f7c2d
sudo -n rm -rf -- /tmp/plan03a-task5-20260825-0415-a91f7c2d
test ! -e /tmp/plan03a-task5-20260825-0415-a91f7c2d
test -z "$(sudo -n docker ps -aq --filter label=com.docker.compose.project=plan03at5a91f7c2d)"
test -z "$(sudo -n docker volume ls -q --filter label=com.docker.compose.project=plan03at5a91f7c2d)"
test -z "$(sudo -n docker network ls -q --filter label=com.docker.compose.project=plan03at5a91f7c2d)"
sudo -n docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}' | sort
sudo -n docker compose ls
```

After writing the final documents, the Windows host ran these checks at
`2026-08-25T04:41:00Z`:

```powershell
docker compose -f docker-compose.yml -f docker-compose.e2e.yml config --quiet
uv run ruff check .
uv run pytest -q -m 'not integration'
```

The Compose command used another runtime-generated 32-byte JWT key and exited 0. Ruff reported
`All checks passed!`. Pytest reported `104 passed, 26 deselected, 1 warning in 4.44s`. The final
local env/document Base64 scan and static secret-assignment scan found zero candidates.

The first Gitleaks run identified a static synthetic JWT value in `docker-compose.e2e.yml`. The E2E
Compose overlay now requires `DARKNETRA_JWT_SIGNING_KEY_B64` from the runtime environment. At the
time of this prior run, the Plan 02 Task 13 workflow wrote a generated masked value to
`GITHUB_ENV`. The final-fix verification above supersedes that workflow design with the scoped
mode-600 `RUNNER_TEMP` env file.

## Security properties exercised

- AES-256-GCM round trips, random nonces, tamper rejection, and purpose/resource AAD binding run in
  the full unit suite.
- HMAC-SHA-256 blind indexes use a separate key and reject encryption-key reuse.
- Runtime settings validate exact 32-byte keys, multiple key versions, and the active version.
- Persistence helpers validate envelopes without a decrypting property, and response model tests
  reject ordinary serialization of envelope internals.
- The real PostgreSQL reveal integration checks persisted effective roles, viewer denial,
  cross-case not-found equivalence, successful decryption, and a committed audit record without
  plaintext.
- Rotation tests retain old decryption versions, fail on unknown versions, produce active-version
  ciphertext, preserve the blind index by default, and rotate it only on an explicit request.

## Limits

- Docker Desktop was unavailable on the Windows host, and Psycopg does not support the host's
  Proactor event loop. Linux/Compose verification on the authorized VM supplied the PostgreSQL and
  Docker evidence.
- GitHub Actions did not supply evidence for this gate. Account billing currently prevents jobs
  from starting, so this record makes no GitHub Actions success claim.
- Plan 03 evidence models are not present at the tested SHA. The architecture document defines the
  consuming-model gate for source locators, authority references, policy-sensitive analyst notes
  and rationales, custody notes, contacts, and policy-restricted wallets. Plan 03 must add model and
  API tests that prove those fields call this boundary before persistence.
