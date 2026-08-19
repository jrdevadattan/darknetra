# Plan 03 Task 4 — fail-closed ingestion policy verification

- **Verified source:** `1715b3dbf8021b8bf2271ee9b25c2e263fbac72f`
- **Observed (UTC):** `2026-08-19T14:16:26Z`
- **Runner:** GitHub Actions `ubuntu-latest`
- **TDD RED evidence:** workflow run `32261195196` failed before production code existed with `ingestion policy module is not implemented`.

| GREEN gate | Outcome |
|---|---|
| Frozen Python workspace | success |
| Alembic upgrade | success |
| Ruff | success |
| Focused ingestion-policy suite (26 tests) | success |
| Complete Python regression suite (130 tests) | success |
| Docker Compose validation | success |
| Independent fail-closed policy smoke | success |

## Verified boundary

- Default artifact limit is 100 MiB; the absolute configurable ceiling is 500 MiB.
- `PUBLIC_OBSERVATION` and `AUTHORIZED_IMPORT` require an authority reference.
- Capture timestamps must be timezone-aware and unknown metadata fields are rejected.
- Detection uses bytes rather than caller filenames.
- Empty, NUL-bearing, non-UTF-8, ELF, PE and shebang executable payloads fail closed.
- Concrete MIME declarations must match detected bytes.
- Approved parser families are PDF, image, ZIP archive, WARC, WARC/GZIP candidate, HTML, JSON, CSV and UTF-8 text.
