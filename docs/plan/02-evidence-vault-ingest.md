# Plan 02 — Evidence vault, upload, ingest parsers, derivatives, custody

Milestone M1 · Owner B · Depends on 01.

**Goal.** Immutable, content-addressed evidence with chain of custody; safe ingestion of PDF, HTML/WARC, images, CSV/JSON, Telegram and WhatsApp chat exports (ZIP), audio placeholders and unknown files; derivatives with spans that later plans cite; quarantine for anything unsafe.

**Architecture.** `evidence/` owns rows, custody and the vault; `ingest/` owns sniffing, parsers and the derivative job. Parsers are pure functions from bytes to typed derivative objects; the service persists them. Nothing executes content. Every derivative records `extractor` and `version` so reprocessing is versioned.

---

## Files

```
darknetra/evidence/
├── models.py          Evidence, CustodyEvent, Derivative
├── codes.py           next_evidence_code(session, case_id) → "E-0007" (per-case counter, gap-free within a transaction)
├── vault.py           VaultBackend Protocol; LocalVault(root)
├── service.py         ingest_upload(), ingest_bytes() (used by capture gate), get(), list(), serve_original(), derivative(), context(), verify(), release_quarantine(), reprocess()
├── custody.py         add_event()
darknetra/ingest/
├── sniff.py           sniff(bytes, filename) → Sniffed(mime, kind, ext_mismatch: bool)
├── quarantine.py      rules → QuarantineDecision(reason)
├── zipsafe.py         safe_members(zf, limits) → iterator; raises ZipUnsafe(reason)
├── parsers/
│   ├── base.py        Derivative dataclasses: TextDoc, Messages, Rows, ImageMeta, HtmlSafe, Pending
│   ├── pdf.py         pypdf → TextDoc(pages, line_offsets)
│   ├── html.py        selectolax + nh3 → TextDoc + HtmlSafe
│   ├── warc.py        warcio → per-response HTML → html.py
│   ├── image.py       Pillow + imagehash → ImageMeta
│   ├── tabular.py     csv/json → Rows
│   ├── telegram.py    result.json / messages*.html → Messages
│   ├── whatsapp.py    chat .txt → Messages
│   └── audio.py       → Pending("TRANSCRIPT_PENDING")
├── dispatch.py        choose parser by Sniffed.kind; registry with versions
├── service.py         process_evidence(evidence_id) job: derive → persist → enqueue chunking (05) and extraction (04)
darknetra/api/v1/routes/evidence.py   (replace stubs)
alembic/versions/0003_evidence.py
tests/unit/ingest/test_sniff.py test_zipsafe.py test_pdf.py test_html.py test_image.py test_tabular.py test_telegram.py test_whatsapp.py
tests/integration/test_upload.py test_dedupe.py test_custody.py test_context.py test_reprocess.py test_quarantine_flow.py
```

---

## Interfaces

### Vault

```python
class VaultBackend(Protocol):
    async def put_stream(self, stream: AsyncIterator[bytes], *, max_bytes: int) -> StoredBlob   # StoredBlob(sha256, size, tmp_path)
    async def commit(self, blob: StoredBlob, key: str) -> None      # move into place, chmod 0o444, write manifest
    def open(self, key: str) -> BinaryIO
    def exists(self, key: str) -> bool
    def path_for(self, key: str) -> Path
class LocalVault(VaultBackend): root/<case_id>/<sha256[:2]>/<sha256>  +  <sha256>.manifest.json
```

Streaming hash: SHA-256 updated per chunk; abort with `Validation("upload exceeds limit")` (413) when `max_bytes` is exceeded before buffering more.

### Evidence service

```python
async def ingest_upload(session, *, case, actor, file: UploadFile, source_class: SourceClass = UPLOAD, note: str | None) -> EvidenceIngestResult
async def ingest_bytes(session, *, case, requester: Requester, data: bytes, filename: str, mime_hint: str | None,
                       source_class: SourceClass, origin: Origin, locator: str | None, captured_at: datetime, meta: dict) -> EvidenceIngestResult
# EvidenceIngestResult(evidence: Evidence, duplicate: bool, warnings: list[str])
```

Flow (both entry points): hash → dedupe by `(case_id, sha256)` → sniff → quarantine rules → allocate code → commit to vault → insert evidence (+ `locator_enc`, `locator_bidx` via `crypto.fields`) → custody `INGESTED` (or `VERIFIED` on duplicate) → audit `evidence.ingest` → submit `process_evidence` job (skipped for QUARANTINED).

### Sniff kinds

`PDF, HTML, WARC, IMAGE, CSV, JSON, TEXT, ZIP, AUDIO, VIDEO, OFFICE, UNKNOWN`. Text detection: valid UTF-8 (or UTF-16 with BOM) with < 5% control characters. Extension mismatch (e.g. `.jpg` that sniffs as ZIP) is a warning; the sniffed kind wins.

### Quarantine rules (any → `QUARANTINED`)

- `OFFICE` (docx/xlsx/pptx) until plan 16 adds a parser; `VIDEO`; `UNKNOWN` binary; executables and scripts (PE/ELF/Mach-O, `.js`, `.vbs`, `.ps1`, `.sh`, `.bat`, `.jar`, `.apk`, `.msi`).
- ZIP that violates `zipsafe` limits: member path with `..` or absolute or drive letter; symlink; total uncompressed > `max_zip_bytes`; ratio > 100:1 for any member; > 2,000 members; nested archive deeper than 1.
- Image decompression bomb (`Image.MAX_IMAGE_PIXELS` exceeded) or > 12,000 px on a side.
- Any image whose evidence `source_class == OSINT_DARK` (quarantined at ingest, releasable).

Quarantined evidence is stored, hashed, listed, downloadable only as an attachment by `EVIDENCE_VIEW_ORIGINAL`, and produces no derivative.

### Derivative types

```python
@dataclass class TextDoc: text: str; line_offsets: list[int]; page_map: list[tuple[int,int]] | None; lang_tags: list[str]; script_tags: list[str]; warnings: list[str]
@dataclass class Message: idx: int; ts: datetime | None; tz: str | None; sender: str | None; text: str; media_refs: list[str]; reply_to: int | None; edited: bool; system: bool
@dataclass class Messages: messages: list[Message]; platform: Literal["telegram","whatsapp","generic"]; warnings: list[str]
@dataclass class Rows: header: list[str]; rows: list[list[str]]; truncated: bool
@dataclass class ImageMeta: width: int; height: int; format: str; exif_present: bool; exif: dict; phash: str; dhash: str
@dataclass class HtmlSafe: html: str
@dataclass class Pending: reason: str
```

Persisted as `derivatives(kind, storage_key → vault JSON/text file, extractor, version, lang_tags, script_tags, text_len, meta)`. `Messages` are also flattened to a `TextDoc` (one line per message: `[idx] ts sender: text`) so spans and chunks work uniformly; `line_offsets` map lines to message indices.

Language and script tagging at ingest: per-line script detection (`Latn/Deva/Guru/Common/Other`) by Unicode ranges; language guess `hi/pa/en/und` from script plus a small stopword list; Hinglish = `Latn` script with Hindi/Punjabi stopwords → tag `hi-Latn`/`pa-Latn`.

### Parser specifics

- **PDF**: `pypdf.PdfReader(strict=False)`; encrypted without password → `Pending("ENCRYPTED")` status PARTIAL; per-page text joined with `\f`; `page_map` records `(start_line, end_line)` per page; empty text on all pages → `Pending("TEXT_NOT_AVAILABLE")`.
- **HTML**: parse with selectolax; drop `script, style, noscript, iframe, object, embed, form, input, link[rel=import], meta[http-equiv], base`; text with block-level newlines; `HtmlSafe` via `nh3.clean(html, tags=basic set, attributes={"a":{"href"}}, link_rel="noopener noreferrer nofollow", url_schemes={"http","https"})` and all `href` rewritten to `#` unless the review role opts in (frontend never follows them).
- **WARC**: iterate `response` records with `text/html`; each becomes a child evidence (origin DERIVATIVE, `parent_evidence_id`), then HTML parsing.
- **Images**: `Image.open` with `MAX_IMAGE_PIXELS = 80e6`; `ImageOps.exif_transpose`; pHash + dHash (imagehash, hash_size 8); EXIF values stored in `meta` but the API returns only `exif_present` unless `EVIDENCE_VIEW_ORIGINAL`.
- **Tabular**: CSV via `csv.Sniffer` (fallback `,`), max 50,000 rows × 64 columns × 2,000 chars; JSON arrays of objects → rows; formulas (`=`, `+`, `-`, `@` leading) kept as text with a warning.
- **Telegram** (Desktop export): `result.json` → `messages[]`; `text` may be a string or a list of `{type, text}` parts (join text of parts, keep `mention`/`link` types as text); `date` ISO local + `date_unixtime`; `from`, `from_id`; `reply_to_message_id`; `photo`/`file` → `media_refs`; `edited` set when `edited` key exists; `type != "message"` → `system=True`. HTML export (`messages.html`, `messages2.html`…): `div.message.default` blocks with `div.from_name`, `div.date[title]`, `div.text`; ordered by file then position.
- **WhatsApp** (`_chat.txt` / `WhatsApp Chat with X.txt`): strip U+200E/U+200F; line regexes, tried in order:
  - Android: `^(\d{1,2}/\d{1,2}/\d{2,4}), (\d{1,2}:\d{2})(?:\s?([ap]\.?m\.?))? - (.+?): (.*)$` (case-insensitive)
  - iOS: `^\[(\d{1,2}/\d{1,2}/\d{2,4}), (\d{1,2}:\d{2}(?::\d{2})?)(?:\s?([AP]M))?\] (.+?): (.*)$`
  - system lines: same prefix without `: ` → `system=True`
  - continuation lines (no prefix) append to the previous message with `\n`.
  - Date order (dd/mm vs mm/dd) inferred from the file: if any first field > 12 → dd/mm; else default dd/mm (India) with a warning. `<Media omitted>`, `image omitted`, `(file attached)` → `media_refs=["omitted"]`.
- **ZIP chat export**: after `zipsafe`, detect platform: contains `result.json` or `messages.html` → Telegram; contains a `.txt` whose first 20 lines match the WhatsApp regex → WhatsApp; media files become child evidence (origin DERIVATIVE) linked by filename in `media_refs`.
- **Audio**: `Pending("TRANSCRIPT_PENDING")`; plan 16 adds IndicConformer.

### Endpoints (replace stubs; schemas in plan 11)

- `POST /cases/{id}/evidence` (multipart `files[]`, `source_class?`, `note?`) → 201 `[EvidenceIngestResult]`; per-file errors returned inline (`{filename, error}`) rather than failing the batch.
- `GET /cases/{id}/evidence?source_class&origin&status&kind&q&cursor&limit`
- `GET /cases/{id}/evidence/{eid}` → Evidence with derivatives summary and custody.
- `GET /cases/{id}/evidence/{eid}/original` (EVIDENCE_VIEW_ORIGINAL) → streamed file; `Content-Disposition: attachment` unless kind ∈ {IMAGE(not quarantined), PDF}; `X-Content-Type-Options: nosniff`; custody `VIEWED_ORIGINAL`.
- `GET /cases/{id}/evidence/{eid}/derivatives/{kind}` → `TextDoc` (with `line_offsets`), `Messages`, `Rows`, `ImageMeta`, or `HtmlSafe` (served with `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`).
- `GET /cases/{id}/evidence/{eid}/context?start&end&pad=200` → `{text, span:{start,end}, line_no, before, after}` bounded to 4,000 chars.
- `POST /cases/{id}/evidence/{eid}/verify` → recompute hash from vault; mismatch → status `FAILED` + custody `VERIFIED(hash_verified=false)` + audit alarm.
- `POST /cases/{id}/evidence/{eid}/release` (EVIDENCE_RELEASE_QUARANTINE) → only for quarantined images; status READY; audit with rationale.
- `POST /cases/{id}/evidence/{eid}/reprocess` → new derivative versions; old rows kept.

### Job

`process_evidence(evidence_id)`: load → dispatch parser by kind → persist derivatives (versioned) → status READY/PARTIAL/FAILED → custody `DERIVED` → `store.changed` event (plan 06 event bus; until then, no-op) → enqueue `rag.index_evidence` (plan 05) and `extract.run_evidence` (plan 04) if text exists.

---

## Tasks

- [ ] **T1 vault**: LocalVault with streaming hash, cap, commit, manifest, read-only files; tests incl. cap abort and duplicate commit idempotency.
- [ ] **T2 codes + models + migration 0003**.
- [ ] **T3 sniff + quarantine + zipsafe**: unit tests with in-memory files: PE header, ELF, script by extension, `.jpg` containing ZIP, traversal member, symlink member, 1 MB → 200 MB ratio bomb, 2,001 members, nested zip.
- [ ] **T4 parsers**: pdf (normal, encrypted, image-only), html (script/iframe/meta-refresh removed; safe html has no `on*` attributes), image (EXIF orientation, bomb), tabular (sniff, caps, formula text), telegram (json parts array, html export), whatsapp (Android 12-hour, iOS bracketed, system lines, continuation, media omitted, LRM).
- [ ] **T5 evidence service**: ingest_upload/ingest_bytes, dedupe, custody, locator encryption + blind index, audit.
- [ ] **T6 endpoints**: list filters, original serving rules, derivatives, context bounds, verify, release, reprocess.
- [ ] **T7 job wiring**: `process_evidence` via `jobs.runner`; status transitions; child evidence for ZIP media and WARC responses.
- [ ] **T8 integration**: upload a ZIP with a Telegram export + 3 images → 1 parent + children; messages derivative correct; quarantine flow (scenario 4); duplicate (scenario 1); 413 (scenario 5, using a small configured cap in tests).

## Acceptance gate

`tests/integration/test_upload.py` uploads the six fixture types and asserts statuses and derivative kinds; `/context` returns the exact substring for a given span; scenarios 1–8 in plan 17 pass.

## Handoff

Plan 04 consumes `TextDoc` derivatives via `evidence.service.derivative(eid, "TEXT")`; plan 05 consumes the same for chunking; plan 08 calls `ingest_bytes` from the capture gate with `origin=CAPTURE|MONITOR`.
