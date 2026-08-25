from alembic.config import CommandLine, Config
from alembic.script import ScriptDirectory
from darknetra_api.db import migration_transitions
from darknetra_api.db.migration_transitions import TransitionPolicy, transition_policy


def test_transition_policy_is_narrowly_scoped_to_published_evidence_revisions() -> None:
    assert transition_policy("b7c19a4e5d20", "upgrade", "head") == TransitionPolicy(
        preflight_b7_identity=True,
        preflight_numeric_downgrade=False,
        adapt_c3_downgrade=False,
    )
    assert transition_policy("c3f80a92d614", "downgrade", "b7c19a4e5d20") == (
        TransitionPolicy(
            preflight_b7_identity=False,
            preflight_numeric_downgrade=True,
            adapt_c3_downgrade=True,
        )
    )
    assert transition_policy("d4e91b7a2c08", "downgrade", "base") == (
        TransitionPolicy(
            preflight_b7_identity=False,
            preflight_numeric_downgrade=True,
            adapt_c3_downgrade=True,
        )
    )

    no_adapter = TransitionPolicy(False, False, False)
    assert transition_policy("d4e91b7a2c08", "downgrade", "c3f80a92d614") == no_adapter
    assert transition_policy("c3f80a92d614", "upgrade", "head") == no_adapter
    assert transition_policy("unrelated", "upgrade", "head") == no_adapter


def test_c3_adapter_replaces_the_callable_used_by_the_active_script_directory() -> None:
    config = Config("apps/api/alembic.ini")
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision(migration_transitions.C3_REVISION)
    assert revision is not None
    assert revision.module.downgrade is not migration_transitions._adapted_c3_downgrade

    revision.module.downgrade = migration_transitions._adapted_c3_downgrade

    [step] = list(
        script._downgrade_revs(
            migration_transitions.B7_REVISION,
            migration_transitions.C3_REVISION,
        )
    )
    assert step.migration_fn is migration_transitions._adapted_c3_downgrade


def test_real_alembic_cli_command_tuple_activates_the_published_transition_policy() -> None:
    options = CommandLine().parser.parse_args(["downgrade", migration_transitions.B7_REVISION])
    command_spec = options.cmd
    assert isinstance(command_spec, tuple)
    command = migration_transitions._command_name(command_spec)

    assert command == "downgrade"
    assert transition_policy(
        migration_transitions.C3_REVISION,
        command,
        options.revision,
    ).adapt_c3_downgrade
