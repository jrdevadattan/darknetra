# Evidence provenance invariants

Evidence starts in `STAGING`. Once it enters any other state, it can never
return to `STAGING`. PostgreSQL triggers, ORM listeners, and the owning service
all enforce that transition rule, so a two-statement state rollback cannot make
the preservation manifest writable again.

Every non-staging artifact requires a nonnegative byte size, canonical lowercase
SHA-256, and an object key matching `^[!-~]+$`: printable non-space ASCII only.
Tabs, newlines, spaces, and Unicode whitespace are rejected identically by the
service, ORM metadata, and PostgreSQL. SHA-512 is optional; when present it must
be canonical lowercase hexadecimal. After staging, byte size, SHA-256, SHA-512,
and object key are immutable.

Derivation parameters are JSONB plus a SHA-256 identity derived from the
versioned canonical JSON representation. PostgreSQL's immutable recursive
canonicalizer and digest function are the authority for direct and bulk writes;
the Python implementation is kept byte-for-byte compatible and validates ORM
writes and loads. Work identity excludes the child ID, so a retry cannot create
duplicate lineage by choosing another child.

Canonical JSON v1 intentionally accepts only integer-valued JSON numbers.
Python integers are retained; finite floats with an exact integer value are
normalized to base-10 integers (`1.0` to `1`, `1e20` to its full integer, and
`-0.0` to `0`). Non-integral and non-finite numbers are rejected. PostgreSQL
applies the same rule recursively to JSONB before digesting, including nested
objects and arrays.

Sensitive envelopes require canonical Base64, not merely decodable Base64.
Both Python and PostgreSQL strictly decode and re-encode each value and require
the stored spelling to match, including zero unused padding bits.

Custody rows are append-only. PostgreSQL rejects UPDATE and DELETE and rejects
TRUNCATE from the runtime role. The application role also lacks those table
privileges and does not own the schema; see
`docs/operations/database-roles.md` for deployment requirements.

Downgrading the invariant revision is lossless for data representable by the
prior schema. If repeated protected values, distinct-parameter lineage, or a
SHA-256-only preserved row cannot fit the targeted historical schema, an early
transactional preflight refuses the downgrade before any DDL or data change.
