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

    def record_tool_call(
        self,
        session_id: str,
        call_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        status: str = "completed",
        duration_ms: Optional[int] = None,
    ) -> str:
        record_id = str(uuid.uuid4())
        safe_args = redact_secrets(json.dumps(arguments))
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tool_calls (id, session_id, call_id, tool_name, arguments, status, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (record_id, session_id, call_id, tool_name, safe_args, status, duration_ms, now_utc),
            )
        return record_id

    def record_tool_result(
        self,
        call_id: str,
        output: str,
        exit_code: Optional[int] = None,
        redaction_metadata: Optional[str] = None,
    ) -> str:
        record_id = str(uuid.uuid4())
        safe_output = redact_secrets(output)
        now_utc = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tool_results (id, call_id, output, exit_code, redaction_metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (record_id, call_id, safe_output, exit_code, redaction_metadata, now_utc),
            )
        return record_id

    def get_tool_calls(self, session_id: str) -> List[Dict[str, Any]]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM tool_calls WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        """Delete session and cascade delete all associated messages, calls, and events."""
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cur.rowcount > 0

    def export_session(self, session_id: str, export_format: str = "markdown") -> str:
        """Export session transcript to Markdown or JSON with secrets redacted."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        messages = self.get_messages(session_id)
        tool_calls = self.get_tool_calls(session_id)

        if export_format.lower() == "json":
            export_dict = {
                "session": session,
                "messages": messages,
                "tool_calls": tool_calls,
            }
            return redact_secrets(json.dumps(export_dict, indent=2))

        # Default: Markdown
        md_lines = [
            f"# Session Transcript: {session['title']}",
            f"- **Session ID:** `{session['id']}`",
            f"- **Provider / Model:** `{session['provider']}/{session['model']}`",
            f"- **Workspace:** `{session['workspace']}`",
            f"- **Created:** `{session['created_at']}`",
            "",
            "---",
            "",
        ]

        for m in messages:
            role_header = f"### {m['role'].capitalize()}"
            md_lines.append(role_header)
            md_lines.append(m["content"] or "*(no text)*")
            md_lines.append("")

        return redact_secrets("\n".join(md_lines))
