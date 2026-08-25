"""harden evidence provenance lifecycle

Revision ID: c3f80a92d614
Revises: b7c19a4e5d20
Create Date: 2026-08-25 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3f80a92d614"
down_revision: str | Sequence[str] | None = "b7c19a4e5d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _install_canonical_derivation_functions() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION darknetra_canonical_jsonb(value jsonb) RETURNS text
        LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
        DECLARE
          value_kind text;
          rendered text;
          numeric_value numeric;
        BEGIN
          value_kind := jsonb_typeof(value);
          IF value_kind = 'object' THEN
            SELECT '{' || COALESCE(
              string_agg(
                to_jsonb(entry.key)::text || ':' || darknetra_canonical_jsonb(entry.value),
                ',' ORDER BY entry.key COLLATE "C"
              ),
              ''
            ) || '}' INTO rendered
            FROM jsonb_each(value) AS entry;
          ELSIF value_kind = 'array' THEN
            SELECT '[' || COALESCE(
              string_agg(
                darknetra_canonical_jsonb(element.value),
                ',' ORDER BY element.ordinality
              ),
              ''
            ) || ']' INTO rendered
            FROM jsonb_array_elements(value) WITH ORDINALITY AS element(value, ordinality);
          ELSIF value_kind = 'number' THEN
            numeric_value := (value #>> '{}')::numeric;
            IF numeric_value = 'NaN'::numeric OR numeric_value <> trunc(numeric_value) THEN
              RAISE EXCEPTION
                'derivation parameters numbers must be finite and integer-valued';
            END IF;
            rendered := trunc(numeric_value)::text;
          ELSE
            rendered := value::text;
          END IF;
          RETURN rendered;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION darknetra_derivation_parameters_digest(value jsonb) RETURNS text
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
          SELECT encode(
            digest(
              convert_to('DARKNETRA-DERIVATION-PARAMETERS', 'UTF8') ||
              decode('00', 'hex') || convert_to('v1', 'UTF8') || decode('00', 'hex') ||
              convert_to(darknetra_canonical_jsonb(value), 'UTF8'),
              'sha256'
            ),
            'hex'
          )
        $$
        """
    )


def upgrade() -> None:
    _install_canonical_derivation_functions()

    op.drop_constraint(
        "ck_evidence_manifest_complete_after_staging",
        "evidence_artifacts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evidence_manifest_complete_after_staging",
        "evidence_artifacts",
        "state = 'STAGING' OR (size_bytes IS NOT NULL AND sha256 IS NOT NULL "
        "AND object_key IS NOT NULL AND object_key ~ '^[!-~]+$')",
    )

    op.drop_constraint(
        "ck_evidence_sensitive_nonce_b64",
        "evidence_sensitive_values",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evidence_sensitive_nonce_b64",
        "evidence_sensitive_values",
        "nonce_b64 ~ '^[A-Za-z0-9+/]{16}$' "
        "AND octet_length(decode(nonce_b64, 'base64')) = 12 "
        "AND translate(encode(decode(nonce_b64, 'base64'), 'base64'), E'\\n\\r', '') "
        "= nonce_b64",
    )
    op.drop_constraint(
        "ck_evidence_sensitive_ciphertext_b64",
        "evidence_sensitive_values",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evidence_sensitive_ciphertext_b64",
        "evidence_sensitive_values",
        "ciphertext_b64 ~ '^([A-Za-z0-9+/]{4})*"
        "([A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$' "
        "AND octet_length(decode(ciphertext_b64, 'base64')) >= 16 "
        "AND translate(encode(decode(ciphertext_b64, 'base64'), 'base64'), E'\\n\\r', '') "
        "= ciphertext_b64",
    )

    op.drop_constraint(
        "ck_evidence_derivation_parameters_digest",
        "evidence_derivations",
        type_="check",
    )
    op.execute(
        "UPDATE evidence_derivations SET parameters_digest = "
        "darknetra_derivation_parameters_digest(parameters_json)"
    )
    op.create_check_constraint(
        "ck_evidence_derivation_parameters_digest",
        "evidence_derivations",
        "parameters_digest = darknetra_derivation_parameters_digest(parameters_json)",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION darknetra_reject_custody_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          custody_owner name;
        BEGIN
          IF TG_OP = 'TRUNCATE' THEN
            SELECT tableowner INTO custody_owner
            FROM pg_tables
            WHERE schemaname = TG_TABLE_SCHEMA AND tablename = TG_TABLE_NAME;
            IF current_user <> custody_owner THEN
              RAISE EXCEPTION 'custody events are append-only';
            END IF;
            RETURN NULL;
          END IF;
          RAISE EXCEPTION 'custody events are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS custody_events_reject_runtime_truncate ON custody_events
        """
    )
    op.execute(
        """
        CREATE TRIGGER custody_events_reject_runtime_truncate
        BEFORE TRUNCATE ON custody_events
        FOR EACH STATEMENT EXECUTE FUNCTION darknetra_reject_custody_mutation()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION darknetra_reject_preserved_manifest_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.state <> 'STAGING' AND NEW.state = 'STAGING' THEN
            RAISE EXCEPTION 'preserved evidence cannot return to staging';
          END IF;
          IF OLD.state <> 'STAGING' AND (
            NEW.size_bytes IS DISTINCT FROM OLD.size_bytes OR
            NEW.sha256 IS DISTINCT FROM OLD.sha256 OR
            NEW.sha512 IS DISTINCT FROM OLD.sha512 OR
            NEW.object_key IS DISTINCT FROM OLD.object_key
          ) THEN
            RAISE EXCEPTION 'preserved evidence manifest cannot be rewritten';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'darknetra_runtime') THEN
            GRANT USAGE ON SCHEMA public TO darknetra_runtime;
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
              TO darknetra_runtime;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO darknetra_runtime;
            REVOKE UPDATE, DELETE, TRUNCATE ON custody_events FROM darknetra_runtime;
            REVOKE CREATE ON SCHEMA public FROM darknetra_runtime;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM evidence_sensitive_values
            GROUP BY evidence_id, kind HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade evidence invariants: repeated protected values require upgraded schema';
          END IF;
          IF EXISTS (
            SELECT 1 FROM evidence_derivations
            GROUP BY parent_evidence_id, child_evidence_id, transformation, transformer_version
            HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade evidence invariants: distinct-parameter lineage requires upgraded schema';
          END IF;
          IF EXISTS (
            SELECT 1 FROM evidence_artifacts
            WHERE state <> 'STAGING' AND sha512 IS NULL
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade evidence invariants: historical b7 requires SHA-512';
          END IF;
        END $$
        """
    )

    op.execute("DROP TRIGGER custody_events_reject_runtime_truncate ON custody_events")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION darknetra_reject_custody_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'custody events are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION darknetra_reject_preserved_manifest_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.state <> 'STAGING' AND (
            NEW.size_bytes IS DISTINCT FROM OLD.size_bytes OR
            NEW.sha256 IS DISTINCT FROM OLD.sha256 OR
            NEW.sha512 IS DISTINCT FROM OLD.sha512 OR
            NEW.object_key IS DISTINCT FROM OLD.object_key
          ) THEN
            RAISE EXCEPTION 'preserved evidence manifest cannot be rewritten';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )

    op.drop_constraint(
        "ck_evidence_derivation_parameters_digest",
        "evidence_derivations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evidence_derivation_parameters_digest",
        "evidence_derivations",
        "parameters_digest ~ '^[0-9a-f]{64}$'",
    )
    op.execute("DROP FUNCTION darknetra_derivation_parameters_digest(jsonb)")
    op.execute("DROP FUNCTION darknetra_canonical_jsonb(jsonb)")

    op.drop_constraint(
        "ck_evidence_sensitive_ciphertext_b64",
        "evidence_sensitive_values",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evidence_sensitive_ciphertext_b64",
        "evidence_sensitive_values",
        "ciphertext_b64 ~ '^([A-Za-z0-9+/]{4})*"
        "([A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$' "
        "AND octet_length(decode(ciphertext_b64, 'base64')) >= 16",
    )
    op.drop_constraint(
        "ck_evidence_sensitive_nonce_b64",
        "evidence_sensitive_values",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evidence_sensitive_nonce_b64",
        "evidence_sensitive_values",
        "nonce_b64 ~ '^[A-Za-z0-9+/]{16}$' "
        "AND octet_length(decode(nonce_b64, 'base64')) = 12",
    )

    op.drop_constraint(
        "ck_evidence_manifest_complete_after_staging",
        "evidence_artifacts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evidence_manifest_complete_after_staging",
        "evidence_artifacts",
        "state = 'STAGING' OR (size_bytes IS NOT NULL AND sha256 IS NOT NULL "
        "AND sha512 IS NOT NULL AND object_key IS NOT NULL)",
    )
