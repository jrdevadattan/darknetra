# ADR-0002: Use UUID4 until an approved UUIDv7 implementation is adopted

- **Status:** Accepted
- **Date:** 2026-08-18
- **Scope:** Plan 02 identity, session, case, membership, and audit records

## Context

The Plan 02 implementation plan prefers application-generated UUIDv7 identifiers when an approved implementation is available, but explicitly permits UUID4 rather than inventing a custom timestamp-ordered UUID algorithm.

The locked Python dependency set does not currently include an approved UUIDv7 package, and Python 3.12 does not provide a standard-library UUIDv7 generator. Creating an ad hoc implementation would add security, interoperability, and maintenance risk to identifiers that cross API, database, audit, and frontend boundaries.

## Decision

DARKNETRA uses Python's standard UUID4 generation for Plan 02 primary keys and request-independent domain identifiers.

The database schema and public API contracts treat identifiers as UUIDs without depending on UUID4-specific ordering. Stable list ordering is supplied explicitly by query fields such as `(updated_at DESC, id DESC)` rather than by assuming timestamp order inside the identifier.

## Consequences

- Identifiers are generated application-side with a well-understood standard implementation.
- No custom UUID bit layout or unreviewed dependency is introduced.
- UUID values are not naturally time ordered; queries must continue to use explicit timestamp ordering.
- A future migration to UUIDv7 may be considered only after selecting and reviewing an approved implementation. Existing UUID4 rows remain valid UUIDs and do not need to be rewritten merely to adopt UUIDv7 for new records.

## Alternatives rejected

- **Custom UUIDv7 implementation:** rejected because identifier generation is security- and compatibility-sensitive infrastructure.
- **Database-generated serial integers:** rejected because identifiers are exposed across case-scoped API boundaries and should not encourage enumeration.
- **ULID or another identifier family:** rejected because it would alter the approved UUID API contract.
