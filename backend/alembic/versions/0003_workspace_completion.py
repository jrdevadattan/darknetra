"""M2/M3 private chats and NIM provider support."""

from alembic import op

revision = "0003_workspace_completion"
down_revision = "0002_report_completion"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE private_threads (\n\towner_user_id UUID NOT NULL, \n\ttitle TEXT NOT NULL, \n\tstatus TEXT NOT NULL, \n\tprovider TEXT NOT NULL, \n\tbudget_usd NUMERIC(12, 4) NOT NULL, \n\tspent_usd NUMERIC(12, 4) NOT NULL, \n\tlast_message_at TIMESTAMP WITH TIME ZONE, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_private_threads PRIMARY KEY (id), \n\tCONSTRAINT uq_private_threads_owner_user_id_id UNIQUE (owner_user_id, id), \n\tCONSTRAINT ck_private_threads_status CHECK (status IN ('OPEN','CLOSED')), \n\tCONSTRAINT ck_private_threads_budget CHECK (budget_usd >= 0 AND spent_usd >= 0), \n\tCONSTRAINT fk_private_threads_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_private_threads_owner_user_id ON private_threads (owner_user_id)")
    op.execute(
        "CREATE TABLE private_runs (\n\towner_user_id UUID NOT NULL, \n\tthread_id UUID NOT NULL, \n\tstatus TEXT NOT NULL, \n\tprovider TEXT NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tcost_usd NUMERIC(12, 4) NOT NULL, \n\ttokens_in INTEGER NOT NULL, \n\ttokens_out INTEGER NOT NULL, \n\tcost_complete BOOLEAN NOT NULL, \n\terror JSONB, \n\tcancel_requested BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tCONSTRAINT pk_private_runs PRIMARY KEY (id), \n\tCONSTRAINT uq_private_runs_owner_user_id_id UNIQUE (owner_user_id, id), \n\tCONSTRAINT uq_private_runs_owner_user_id_thread_id_id UNIQUE (owner_user_id, thread_id, id), \n\tCONSTRAINT fk_private_runs_owner_user_id_private_threads FOREIGN KEY(owner_user_id, thread_id) REFERENCES private_threads (owner_user_id, id), \n\tCONSTRAINT ck_private_runs_status CHECK (status IN ('QUEUED','RUNNING','DONE','ERROR','CANCELLED','BUDGET')), \n\tCONSTRAINT fk_private_runs_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_private_runs_owner_user_id ON private_runs (owner_user_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_private_runs_active_thread ON private_runs (thread_id) WHERE status IN ('QUEUED','RUNNING')"
    )
    op.execute(
        "CREATE TABLE private_messages (\n\towner_user_id UUID NOT NULL, \n\tthread_id UUID NOT NULL, \n\trun_id UUID, \n\trole TEXT NOT NULL, \n\ttext TEXT NOT NULL, \n\tblocks JSONB NOT NULL, \n\tprovider TEXT, \n\tat TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tCONSTRAINT pk_private_messages PRIMARY KEY (id), \n\tCONSTRAINT fk_private_messages_owner_user_id_private_threads FOREIGN KEY(owner_user_id, thread_id) REFERENCES private_threads (owner_user_id, id), \n\tCONSTRAINT fk_private_messages_owner_user_id_private_runs FOREIGN KEY(owner_user_id, thread_id, run_id) REFERENCES private_runs (owner_user_id, thread_id, id), \n\tCONSTRAINT ck_private_messages_role CHECK (role IN ('USER','ASSISTANT','SYSTEM'))\n)"
    )
    op.execute("CREATE INDEX ix_private_messages_owner_user_id ON private_messages (owner_user_id)")
    op.execute(
        "CREATE TABLE private_run_events (\n\towner_user_id UUID NOT NULL, \n\trun_id UUID NOT NULL, \n\tseq INTEGER NOT NULL, \n\ttype TEXT NOT NULL, \n\tdata JSONB NOT NULL, \n\tat TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tCONSTRAINT pk_private_run_events PRIMARY KEY (run_id, seq), \n\tCONSTRAINT fk_private_run_events_owner_user_id_private_runs FOREIGN KEY(owner_user_id, run_id) REFERENCES private_runs (owner_user_id, id)\n)"
    )
    op.execute(
        "CREATE INDEX ix_private_run_events_owner_user_id ON private_run_events (owner_user_id)"
    )
    op.execute("ALTER TABLE threads DROP CONSTRAINT ck_threads_harness")
    for table in ("private_messages", "private_run_events"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION darknetra_append_only()"
        )
    op.execute(
        "ALTER TABLE threads ADD CONSTRAINT ck_threads_harness CHECK (harness IN ('CLAUDE','OFFLINE','FAKE','DETERMINISTIC','NIM'))"
    )
    op.execute("ALTER TABLE runs DROP CONSTRAINT ck_runs_harness")
    op.execute(
        "ALTER TABLE runs ADD CONSTRAINT ck_runs_harness CHECK (harness IN ('CLAUDE','OFFLINE','FAKE','DETERMINISTIC','NIM'))"
    )
    op.execute("ALTER TABLE messages DROP CONSTRAINT ck_messages_harness")
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT ck_messages_harness CHECK (harness IN ('CLAUDE','OFFLINE','FAKE','DETERMINISTIC','NIM'))"
    )
    op.execute("ALTER TABLE replay_entries DROP CONSTRAINT ck_replay_entries_harness")
    op.execute(
        "ALTER TABLE replay_entries ADD CONSTRAINT ck_replay_entries_harness CHECK (harness IN ('CLAUDE','OFFLINE','FAKE','DETERMINISTIC','NIM'))"
    )


def downgrade():
    raise RuntimeError("Private chat history must be retained; destructive downgrade is disabled")
