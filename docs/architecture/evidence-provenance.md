# Evidence provenance invariants

Evidence starts in `STAGING`. Once it enters any other state, it can never
return to `STAGING`. PostgreSQL triggers, ORM listeners, and the owning service
all enforce that transition rule, so a two-statement state rollback cannot make
the preservation manifest writable again.

Every non-staging artifact requires a nonnegative byte size, canonical lowercase
SHA-256, and a nonblank object key. SHA-512 is optional; when present it must be
canonical lowercase hexadecimal. After staging, byte size, SHA-256, SHA-512,
and object key are immutable.

Derivation parameters are JSONB plus a SHA-256 identity derived from the
versioned canonical JSON representation. PostgreSQL's immutable recursive
canonicalizer and digest function are the authority for direct and bulk writes;
the Python implementation is kept byte-for-byte compatible and validates ORM
writes and loads. Work identity excludes the child ID, so a retry cannot create
duplicate lineage by choosing another child.

Sensitive envelopes require canonical Base64, not merely decodable Base64.
Both Python and PostgreSQL strictly decode and re-encode each value and require
the stored spelling to match, including zero unused padding bits.

Custody rows are append-only. PostgreSQL rejects UPDATE and DELETE and rejects
TRUNCATE from the runtime role. The application role also lacks those table
privileges and does not own the schema; see
`docs/operations/database-roles.md` for deployment requirements.

Downgrading the invariant revision is lossless for data representable by the
prior schema. If repeated protected values or distinct-parameter lineage cannot
fit the prior unique constraints, an early transactional preflight refuses the
downgrade before any DDL or data change.
