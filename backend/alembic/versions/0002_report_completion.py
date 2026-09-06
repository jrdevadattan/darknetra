"""M6 report finalization is write-once; pending jobs may transition to a terminal state.

Revision ID: 0002_report_completion
Revises: 0001_foundation
"""

from alembic import op

revision = "0002_report_completion"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE FUNCTION darknetra_report_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status NOT IN ('QUEUED', 'RUNNING') THEN
        RAISE EXCEPTION 'completed report is immutable';
      END IF;
      IF NEW.status NOT IN ('RUNNING', 'DONE', 'ERROR')
         OR (OLD.status = 'RUNNING' AND NEW.status NOT IN ('RUNNING', 'DONE', 'ERROR')) THEN
        RAISE EXCEPTION 'invalid report transition';
      END IF;
      IF ROW(NEW.id,NEW.case_id,NEW.version,NEW.generated_by,NEW.at,NEW.created_at)
         IS DISTINCT FROM ROW(OLD.id,OLD.case_id,OLD.version,OLD.generated_by,OLD.at,OLD.created_at) THEN
        RAISE EXCEPTION 'report identity and version are immutable';
      END IF;
      IF NEW.status = 'DONE' AND (NEW.evidence_id IS NULL OR NEW.sha256 IS NULL
         OR NEW.storage_key_md IS NULL OR NEW.storage_key_html IS NULL) THEN
        RAISE EXCEPTION 'complete report requires immutable artifacts';
      END IF;
      RETURN NEW;
    END $$
    """)
    op.execute(
        "CREATE TRIGGER reports_immutable BEFORE UPDATE ON reports FOR EACH ROW EXECUTE FUNCTION darknetra_report_immutable()"
    )
    op.execute("CREATE INDEX ix_monitor_hits_case_at ON monitor_hits (case_id, at)")
    op.execute("CREATE INDEX ix_monitor_runs_case_started ON monitor_runs (case_id, started_at)")
    op.execute("CREATE INDEX ix_alerts_case_status_at ON alerts (case_id, status, at)")
    op.execute("CREATE INDEX ix_watchlist_items_due ON watchlist_items (next_run_at) WHERE active")


def downgrade():
    raise RuntimeError("Immutable report enforcement cannot be removed by downgrade")
