"""Narrow compatibility guards for published evidence migration revisions.

The published c3 revision cannot be edited. Its downgrade has two obsolete
shape preflights, and its upgrade can hit a raw uniqueness error before a child
revision runs. This module adapts only the exact b7/c3/d4 crossings while still
executing every c3 downgrade operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op
from alembic.script import ScriptDirectory
from alembic.util import CommandError

from darknetra_api.services.provenance import derivation_parameters_digest

B7_REVISION = "b7c19a4e5d20"
C3_REVISION = "c3f80a92d614"
D4_REVISION = "d4e91b7a2c08"


@dataclass(frozen=True)
class TransitionPolicy:
    preflight_b7_identity: bool
    preflight_numeric_downgrade: bool
    adapt_c3_downgrade: bool


def transition_policy(
    current_revision: str | None,
    command_name: str,
    destination: str | None,
) -> TransitionPolicy:
    destination = destination or ""
    b7_upgrade_targets = {"head", "heads", C3_REVISION, D4_REVISION, "+1"}
    b7_downgrade_targets = {"base", B7_REVISION}
    if current_revision == C3_REVISION:
        b7_downgrade_targets.add("-1")

    return TransitionPolicy(
        preflight_b7_identity=(
            current_revision == B7_REVISION
            and command_name == "upgrade"
            and destination in b7_upgrade_targets
        ),
        preflight_numeric_downgrade=(
            current_revision in {C3_REVISION, D4_REVISION}
            and command_name == "downgrade"
            and destination in b7_downgrade_targets
        ),
        adapt_c3_downgrade=(
            current_revision in {C3_REVISION, D4_REVISION}
            and command_name == "downgrade"
            and destination in b7_downgrade_targets
        ),
    )


def _current_revision(connection: Any) -> str | None:
    if not sa.inspect(connection).has_table("alembic_version"):
        return None
    return connection.scalar(sa.text("SELECT version_num FROM alembic_version"))


def _contains_json_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return False
    if isinstance(value, (int, float, Decimal)):
        return True
    if isinstance(value, list):
        return any(_contains_json_number(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_json_number(item) for item in value.values())
    raise CommandError("cannot inspect derivation parameters for numeric downgrade safety")


def _command_name(command_spec: Any) -> str:
    if isinstance(command_spec, (list, tuple)):
        command_spec = command_spec[0] if command_spec else None
    return getattr(command_spec, "__name__", "")


def _preflight_b7_identity(connection: Any) -> None:
    identities: set[tuple[Any, ...]] = set()
    rows = connection.execute(
        sa.text(
            "SELECT parent_evidence_id, transformation, transformer_version, "
            "parameters_json FROM evidence_derivations"
        )
    ).mappings()
    try:
        for row in rows:
            identity = (
                row["parent_evidence_id"],
                row["transformation"],
                row["transformer_version"],
                derivation_parameters_digest(row["parameters_json"]),
            )
            if identity in identities:
                raise CommandError(
                    "cannot upgrade evidence invariants: canonical derivation "
                    "identities collide before c3"
                )
            identities.add(identity)
    except ValueError as exc:
        raise CommandError(
            "cannot upgrade evidence invariants: historical derivation parameters "
            "are outside the current canonical domain"
        ) from exc


def _preflight_numeric_downgrade(connection: Any) -> None:
    parameters = connection.scalars(
        sa.text("SELECT parameters_json FROM evidence_derivations")
    )
    if any(_contains_json_number(value) for value in parameters):
        raise CommandError(
            "cannot downgrade evidence invariants: numeric derivation parameters "
            "have ambiguous historical JSON tokens"
        )


def _adapted_c3_downgrade() -> None:
    """Execute published c3's full downgrade without its two false shape guards."""
    op.execute(
        """
        DO $$
        BEGIN
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


def prepare_evidence_transition(
    connection: Any,
    alembic_config: Any,
    script_directory: ScriptDirectory,
) -> None:
    options = getattr(alembic_config, "cmd_opts", None)
    command = _command_name(getattr(options, "cmd", None))
    destination = getattr(options, "revision", None)
    if isinstance(destination, (list, tuple)):
        destination = destination[0] if len(destination) == 1 else None
    current = _current_revision(connection)
    policy = transition_policy(current, command, destination)

    if policy.preflight_b7_identity:
        _preflight_b7_identity(connection)
    if policy.preflight_numeric_downgrade:
        _preflight_numeric_downgrade(connection)
    if policy.adapt_c3_downgrade:
        # Alembic constructs RevisionStep objects from the EnvironmentContext's
        # ScriptDirectory. Loading another directory here creates a distinct
        # module and does not replace the executable migration callable.
        revision = script_directory.get_revision(C3_REVISION)
        if revision is None:
            raise CommandError("published c3 evidence revision is unavailable")
        revision.module.downgrade = _adapted_c3_downgrade


__all__ = ["TransitionPolicy", "prepare_evidence_transition", "transition_policy"]
