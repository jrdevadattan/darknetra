"""enforce evidence provenance invariants

Revision ID: b7c19a4e5d20
Revises: 8a7f2d91c402
Create Date: 2026-08-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c19a4e5d20"
down_revision: str | Sequence[str] | None = "8a7f2d91c402"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE FUNCTION darknetra_canonical_jsonb(value jsonb) RETURNS text
        LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
        DECLARE
          value_kind text;
          rendered text;
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
        CREATE FUNCTION darknetra_derivation_parameters_digest(value jsonb) RETURNS text
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
    op.drop_constraint(
        "fk_custody_event_sensitive_note_scope",
        "custody_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_evidence_sensitive_value_artifact_case",
        "evidence_sensitive_values",
        type_="unique",
    )
    op.drop_constraint(
        "uq_evidence_sensitive_value_artifact_kind",
        "evidence_sensitive_values",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_evidence_sensitive_value_identity_scope",
        "evidence_sensitive_values",
        ["id", "evidence_id", "case_id", "kind"],
    )
    op.add_column(
        "custody_events",
        sa.Column(
            "sensitive_note_kind",
            postgresql.ENUM(name="evidence_sensitive_value_kind", create_type=False),
            nullable=True,
        ),
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM custody_events c
            JOIN evidence_sensitive_values s ON s.id = c.sensitive_note_id
            WHERE c.sensitive_note_id IS NOT NULL AND s.kind <> 'CUSTODY_NOTE'
          ) THEN
            RAISE EXCEPTION 'custody sensitive note references a non-custody value';
          END IF;
        END $$
        """
    )
    op.execute(
        "UPDATE custody_events SET sensitive_note_kind = 'CUSTODY_NOTE' "
        "WHERE sensitive_note_id IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_custody_event_sensitive_note_kind",
        "custody_events",
        "(sensitive_note_id IS NULL AND sensitive_note_kind IS NULL) OR "
        "(sensitive_note_id IS NOT NULL AND sensitive_note_kind = 'CUSTODY_NOTE')",
    )
    op.create_foreign_key(
        "fk_custody_event_sensitive_note_scope",
        "custody_events",
        "evidence_sensitive_values",
        ["sensitive_note_id", "evidence_id", "case_id", "sensitive_note_kind"],
        ["id", "evidence_id", "case_id", "kind"],
        ondelete="RESTRICT",
    )

    op.create_check_constraint(
        "ck_evidence_manifest_complete_after_staging",
        "evidence_artifacts",
        "state = 'STAGING' OR (size_bytes IS NOT NULL AND sha256 IS NOT NULL "
        "AND object_key IS NOT NULL AND btrim(object_key) <> '')",
    )
    op.create_check_constraint(
        "ck_evidence_sensitive_key_version",
        "evidence_sensitive_values",
        "key_version ~ '^v[1-9][0-9]{0,62}$'",
    )
    op.create_check_constraint(
        "ck_evidence_sensitive_nonce_b64",
        "evidence_sensitive_values",
        "nonce_b64 ~ '^[A-Za-z0-9+/]{16}$' "
        "AND octet_length(decode(nonce_b64, 'base64')) = 12 "
        "AND translate(encode(decode(nonce_b64, 'base64'), 'base64'), E'\\n\\r', '') "
        "= nonce_b64",
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
    op.create_check_constraint(
        "ck_evidence_sensitive_blind_index_policy",
        "evidence_sensitive_values",
        "(kind = 'SOURCE_LOCATOR' AND blind_index IS NOT NULL) OR "
        "(kind <> 'SOURCE_LOCATOR' AND blind_index IS NULL)",
    )

    op.drop_constraint(
        "uq_evidence_derivation_identity",
        "evidence_derivations",
        type_="unique",
    )
    op.add_column(
        "evidence_derivations",
        sa.Column("parameters_digest", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE evidence_derivations SET parameters_digest = "
        "darknetra_derivation_parameters_digest(parameters_json)"
    )
    op.alter_column("evidence_derivations", "parameters_digest", nullable=False)
    op.create_check_constraint(
        "ck_evidence_derivation_parameters_digest",
        "evidence_derivations",
        "parameters_digest = darknetra_derivation_parameters_digest(parameters_json)",
    )
    op.create_unique_constraint(
        "uq_evidence_derivation_work_identity",
        "evidence_derivations",
        ["parent_evidence_id", "transformation", "transformer_version", "parameters_digest"],
    )

    op.execute(
        """
        CREATE FUNCTION darknetra_reject_custody_mutation() RETURNS trigger
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
        CREATE TRIGGER custody_events_append_only
        BEFORE UPDATE OR DELETE ON custody_events
        FOR EACH ROW EXECUTE FUNCTION darknetra_reject_custody_mutation()
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
        CREATE FUNCTION darknetra_reject_preserved_manifest_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
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
        CREATE TRIGGER evidence_manifest_immutable
        BEFORE UPDATE ON evidence_artifacts
        FOR EACH ROW EXECUTE FUNCTION darknetra_reject_preserved_manifest_mutation()
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
        END $$
        """
    )
    op.execute("DROP TRIGGER evidence_manifest_immutable ON evidence_artifacts")
    op.execute("DROP FUNCTION darknetra_reject_preserved_manifest_mutation()")
    op.execute("DROP TRIGGER custody_events_reject_runtime_truncate ON custody_events")
    op.execute("DROP TRIGGER custody_events_append_only ON custody_events")
    op.execute("DROP FUNCTION darknetra_reject_custody_mutation()")

    op.drop_constraint(
        "uq_evidence_derivation_work_identity",
        "evidence_derivations",
        type_="unique",
    )
    op.drop_constraint(
        "ck_evidence_derivation_parameters_digest",
        "evidence_derivations",
        type_="check",
    )
    op.drop_column("evidence_derivations", "parameters_digest")
    op.execute("DROP FUNCTION darknetra_derivation_parameters_digest(jsonb)")
    op.execute("DROP FUNCTION darknetra_canonical_jsonb(jsonb)")
    op.create_unique_constraint(
        "uq_evidence_derivation_identity",
        "evidence_derivations",
        ["parent_evidence_id", "child_evidence_id", "transformation", "transformer_version"],
    )

    for constraint in (
        "ck_evidence_sensitive_blind_index_policy",
        "ck_evidence_sensitive_ciphertext_b64",
        "ck_evidence_sensitive_nonce_b64",
        "ck_evidence_sensitive_key_version",
    ):
        op.drop_constraint(constraint, "evidence_sensitive_values", type_="check")
    op.drop_constraint(
        "ck_evidence_manifest_complete_after_staging",
        "evidence_artifacts",
        type_="check",
    )

    op.drop_constraint(
        "fk_custody_event_sensitive_note_scope",
        "custody_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_custody_event_sensitive_note_kind",
        "custody_events",
        type_="check",
    )
    op.drop_column("custody_events", "sensitive_note_kind")
    op.drop_constraint(
        "uq_evidence_sensitive_value_identity_scope",
        "evidence_sensitive_values",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_evidence_sensitive_value_artifact_case",
        "evidence_sensitive_values",
        ["id", "evidence_id", "case_id"],
    )
    op.create_unique_constraint(
        "uq_evidence_sensitive_value_artifact_kind",
        "evidence_sensitive_values",
        ["evidence_id", "kind"],
    )
    op.create_foreign_key(
        "fk_custody_event_sensitive_note_scope",
        "custody_events",
        "evidence_sensitive_values",
        ["sensitive_note_id", "evidence_id", "case_id"],
        ["id", "evidence_id", "case_id"],
        ondelete="RESTRICT",
    )
