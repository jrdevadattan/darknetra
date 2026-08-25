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
Python integers are retained. For a finite float, Python first emits the exact
JSON number token with `json.dumps(..., allow_nan=False)`, parses that token as
an exact decimal, and accepts it only when the decimal is mathematically
integral. It then writes the full base-10 integer (`1.0` to `1`, `1e23` and
`1e30` to their decimal integers, and `-0.0` to `0`). This token rule avoids
deriving identity from binary floating-point approximation. Non-integral and
non-finite numbers are rejected. PostgreSQL applies the same rule recursively
to JSONB, including nested objects, arrays, negative exponents, and arbitrarily
large integers.

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
For compatible rows, the migration rewrites every derivation digest with the
historical-b7 canonicalizer before restoring the historical check, so a retry
under the old application identity remains blocked. Upgrade likewise refuses
historical rows that would collapse to one current canonical work identity.
