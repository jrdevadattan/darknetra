"""finalize evidence transition compatibility

Revision ID: d4e91b7a2c08
Revises: c3f80a92d614
Create Date: 2026-08-25 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4e91b7a2c08"
down_revision: str | Sequence[str] | None = "c3f80a92d614"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _install_bounded_canonical_json() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION darknetra_canonical_jsonb(value jsonb) RETURNS text
        LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
        DECLARE
          value_kind text;
          rendered text;
          numeric_value numeric;
          numeric_text text;
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
            numeric_text := trunc(numeric_value)::text;
            IF length(trim(leading '-' FROM numeric_text)) > 1000 THEN
              RAISE EXCEPTION
                'derivation parameters integers must contain at most 1,000 decimal digits';
            END IF;
            rendered := numeric_text;
          ELSE
            rendered := value::text;
          END IF;
          RETURN rendered;
        END;
        $$
        """
    )


def _install_numeric_tree_detector() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION darknetra_jsonb_contains_number(value jsonb)
        RETURNS boolean LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
        DECLARE
          value_kind text;
          contains_number boolean;
        BEGIN
          value_kind := jsonb_typeof(value);
          IF value_kind = 'number' THEN
            RETURN true;
          ELSIF value_kind = 'object' THEN
            SELECT COALESCE(bool_or(darknetra_jsonb_contains_number(entry.value)), false)
            INTO contains_number FROM jsonb_each(value) AS entry;
            RETURN contains_number;
          ELSIF value_kind = 'array' THEN
            SELECT COALESCE(bool_or(darknetra_jsonb_contains_number(element.value)), false)
            INTO contains_number FROM jsonb_array_elements(value) AS element(value);
            RETURN contains_number;
          END IF;
          RETURN false;
        END;
        $$
        """
    )


def _restore_published_c3_canonical_json() -> None:
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


def upgrade() -> None:
    _install_bounded_canonical_json()
    _install_numeric_tree_detector()
    op.execute(
        """
        DO $$
        BEGIN
          PERFORM darknetra_derivation_parameters_digest(parameters_json)
          FROM evidence_derivations;
        EXCEPTION
          WHEN OTHERS THEN
            RAISE EXCEPTION 'cannot upgrade final evidence invariants: %', SQLERRM;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM evidence_derivations
            WHERE darknetra_jsonb_contains_number(parameters_json)
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade evidence invariants: numeric derivation parameters '
              'have ambiguous historical JSON tokens';
          END IF;
        END $$
        """
    )
    _restore_published_c3_canonical_json()
    op.execute("DROP FUNCTION darknetra_jsonb_contains_number(jsonb)")
