"""SQLite-backed workflow checkpointer for state persistence and safe resumption (Section 11.3)."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from Relay.storage.database import Database
from Relay.utils.logging import redact_secrets
from Relay.workflows.state import WorkflowState


class WorkflowCheckpointer:
    """Saves and restores WorkflowState checkpoints to the SQLite database."""

    def __init__(self, db: Database):
        self.db = db

    def save_checkpoint(
        self,
        workflow_id: str,
        session_id: str,
        graph_id: str,
        state: WorkflowState,
        status: str = "running",
    ) -> str:
        """Persist a state checkpoint with secrets redacted."""
        run_id = workflow_id or str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        state_json = redact_secrets(state.model_dump_json())

        with self.db.transaction() as conn:
            # Ensure parent session exists to satisfy FK constraint
            sess_row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not sess_row:
                conn.execute(
                    """
                    INSERT INTO sessions (id, workspace, provider, model, title, created_at, updated_at, status)
                    VALUES (?, ?, 'default', 'default', 'Workflow session', ?, ?, 'active')
                    """,
                    (session_id, state.workspace or ".", now_utc, now_utc),
                )

            conn.execute(
                """
                INSERT INTO workflow_runs (id, session_id, graph_id, status, checkpoint_ref, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    checkpoint_ref = excluded.checkpoint_ref,
                    updated_at = excluded.updated_at
                """,
                (run_id, session_id, graph_id, status, state_json, now_utc, now_utc),
            )
        return run_id

    def load_checkpoint(self, workflow_id: str) -> Optional[WorkflowState]:
        """Restore a WorkflowState from SQLite checkpoint."""
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM workflow_runs WHERE id = ?",
                (workflow_id,),
            ).fetchone()
            if not row or not row["checkpoint_ref"]:
                return None

            try:
                data = json.loads(row["checkpoint_ref"])
                return WorkflowState(**data)
            except Exception:
                return None

    def list_workflow_runs(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List persisted workflow runs for session."""
        with self.db.transaction() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT id, session_id, graph_id, status, created_at, updated_at FROM workflow_runs WHERE session_id = ? ORDER BY updated_at DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, session_id, graph_id, status, created_at, updated_at FROM workflow_runs ORDER BY updated_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
