"""Session persistence, message history, and change tracking (Section 12)."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Relay.storage.database import Database
from Relay.utils.logging import redact_secrets


class SessionStore:
    """Manages session lifecycle, message logs, and file changes."""

    def __init__(self, db: Database):
        self.db = db

    def create_session(
        self,
        workspace: Path,
        provider: str,
        model: str,
        title: str = "New session",
    ) -> str:
        session_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, workspace, provider, model, title, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (session_id, str(workspace.resolve()), provider, model, title, now_utc, now_utc),
            )
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def list_sessions(self, workspace: Optional[Path] = None) -> List[Dict[str, Any]]:
        with self.db.transaction() as conn:
            if workspace:
                ws_str = str(workspace.resolve())
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE workspace = ? ORDER BY updated_at DESC",
                    (ws_str,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY updated_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    def update_session_title(self, session_id: str, title: str) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title, now_utc, session_id),
            )

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        msg_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        safe_content = redact_secrets(content)
        raw_json = redact_secrets(json.dumps(raw_payload)) if raw_payload else None

        with self.db.transaction() as conn:
            seq_row = conn.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 AS next_seq FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            next_seq = seq_row["next_seq"]

            conn.execute(
                """
                INSERT INTO messages (id, session_id, sequence, role, content, raw_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, session_id, next_seq, role, safe_content, raw_json, now_utc),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now_utc, session_id),
            )
        return msg_id

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY sequence ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def record_file_change(
        self,
        session_id: str,
        path: str,
        before_hash: Optional[str],
        after_hash: Optional[str],
        diff: Optional[str],
    ) -> str:
        change_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO file_changes (id, session_id, path, before_hash, after_hash, diff, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (change_id, session_id, path, before_hash, after_hash, diff, now_utc),
            )
        return change_id
