"""SQLite database management with WAL mode and migration runner (Section 12)."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from contextlib import contextmanager

from Relay.utils.errors import DatabaseError


class Database:
    """SQLite wrapper enforcing WAL mode, foreign keys, and migration integrity."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Database transaction failed: {e}") from e
        finally:
            conn.close()

    def run_migrations(self) -> None:
        """Run all pending SQL migrations in the migrations directory."""
        migrations_dir = Path(__file__).resolve().parent / "migrations"
        if not migrations_dir.is_dir():
            return

        with self.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }

            migration_files = sorted(migrations_dir.glob("*.sql"))
            for mf in migration_files:
                parts = mf.stem.split("_", 1)
                if not parts[0].isdigit():
                    continue
                version = int(parts[0])
                name = parts[1] if len(parts) > 1 else mf.stem

                if version not in applied:
                    sql = mf.read_text(encoding="utf-8")
                    conn.executescript(sql)
                    now_utc = datetime.now(timezone.utc).isoformat()
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (version, name, now_utc),
                    )
