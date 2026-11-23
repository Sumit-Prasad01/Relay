from pathlib import Path
import pytest
from Relay.storage.database import Database


def test_database_creation_and_migrations(tmp_path):
    db_file = tmp_path / "test_state.db"
    db = Database(db_file)
    db.run_migrations()

    assert db_file.is_file()

    with db.transaction() as conn:
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert mode.lower() == "wal"

        migrations = conn.execute("SELECT version, name FROM schema_migrations;").fetchall()
        assert len(migrations) >= 1
        assert migrations[0]["version"] == 1

        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        }
        expected = {
            "schema_migrations",
            "sessions",
            "messages",
            "tool_calls",
            "tool_results",
            "file_changes",
            "approvals",
            "workflow_runs",
            "events",
        }
        assert expected.issubset(tables)
