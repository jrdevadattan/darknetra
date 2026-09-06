"""Apply migrations as the owner, then grant the restricted API role its permissions."""

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from darknetra.config import get_settings


def main() -> None:
    settings = get_settings()
    url = settings.migration_database_url or settings.database_url
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.begin() as conn:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname='darknetra_app'")).scalar():
            conn.execute(text("GRANT USAGE ON SCHEMA public TO darknetra_app"))
            conn.execute(
                text("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO darknetra_app")
            )
            conn.execute(
                text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO darknetra_app")
            )
            conn.execute(
                text(
                    "REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM darknetra_app"
                )
            )
            conn.execute(
                text(
                    "REVOKE UPDATE ON audit_events, decisions, custody_events, derivatives, reports FROM darknetra_app"
                )
            )
            conn.execute(
                text(
                    "GRANT UPDATE (evidence_id, storage_key_md, storage_key_html, sha256, includes, claim_check, redaction, status, error) ON reports TO darknetra_app"
                )
            )
            for table in (
                "chunks",
                "rate_counters",
                "replay_entries",
                "monitor_seen_urls",
                "case_memberships",
                "taxonomy_terms",
            ):
                conn.execute(text(f"GRANT DELETE ON {table} TO darknetra_app"))
    engine.dispose()


if __name__ == "__main__":
    main()
