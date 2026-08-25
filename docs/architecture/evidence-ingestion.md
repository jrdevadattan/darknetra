# Evidence upload and preservation

`POST /api/v1/cases/{case_id}/evidence` accepts one multipart `file` and one JSON
`metadata` field. Case owners and collectors can upload evidence when their current
case membership grants the same role. The endpoint applies the existing authentication,
CSRF, forced-password-change, and case anti-enumeration rules before it asks Starlette
to parse or spool any multipart body bytes.

The file limit defaults to 100 MiB through
`DARKNETRA_EVIDENCE_UPLOAD_MAX_BYTES`. Configuration cannot exceed 500 MiB. An ASGI
receive wrapper limits the full multipart request to the file policy plus a 64 KiB
envelope allowance while bytes arrive. Crossing that boundary raises a private receive
signal which aborts multipart parsing immediately; it is never converted into a normal
end-of-body event. A second wrapper counts the file bytes and stops at limit plus one.
It supplies bounded reads to the storage layer and replays the MIME inspection prefix
without changing the stored digest.

The classifier reads at most 64 KiB and recognizes WARC, WARC.GZ, HTML, XHTML, UTF-8
text, JSON, CSV, ZIP, PNG, JPEG, WebP, and PDF. It rejects executable signatures,
unknown binary input, empty files, malformed complete JSON or gzip signatures, known
extension spoofing, and client MIME disagreements. The byte classification must match
the metadata source type. UTF-8 and control-byte validation continues over every stored
byte for text, HTML/XHTML, CSV, and JSON. JSON additionally uses a bounded-memory
streaming syntax validator with a fixed nesting ceiling, so a valid prefix cannot hide
a binary or malformed tail.

The API runs upload-file access and `LocalObjectStore.put_verified` in one worker thread.
The object store promotes and verifies the content-addressed object before PostgreSQL
receives metadata. If PostgreSQL later rejects the transaction, the API retains the
object as an orphan. A later reconciliation process can remove unreferenced objects;
request failure code must not remove a final object that another row may share.

One PostgreSQL commit creates the `PRESERVED` artifact, protected source fields,
`EVIDENCE_INGESTED`, `CUSTODY_CREATED`, and a `PENDING` job. Source locator uses the
documented exact-match blind index. Authority reference and protected note omit blind
indexes. Audit and custody metadata contain source classifications, media type, size,
and digest. They omit plaintext protected fields and the original filename.

The runtime SQLAlchemy engine hides all bound parameters in exception rendering. An
expected or unexpected persistence failure is rolled back, logged only with the stable
`EVIDENCE_PERSISTENCE_FAILED` code, case ID, and exception type, and returned as a
redacted retryable response. Exception text, SQL parameters, envelopes, blind indexes,
object paths, and broker details are never logged at this boundary.

After commit, Celery receives `job_id`, `case_id`, `evidence_id`, and `pipeline_version`
as JSON strings. A publish error leaves the PostgreSQL job in `PENDING` and the endpoint
returns `202` with `dispatch_state=PENDING_RETRY`. Identical bytes can create separate
evidence rows and share the same content-addressed object when the request supplies no
whole-ingest idempotency key. PostgreSQL still enforces one pipeline job for each
evidence ID and pipeline version.

The response contains evidence and job identifiers, media type, size, SHA-256, and
states. It omits protected plaintext, envelope fields, blind indexes, object keys,
filesystem paths, and broker configuration.
