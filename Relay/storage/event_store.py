"""Structured event logging store with correlation IDs (Section 17)."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from Relay.storage.database import Database
from Relay.utils.logging import redact_secrets


class EventStore:
    """Appends and queries structured audit events."""

    def __init__(self, db: Database):
        self.db = db

    def record_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Record an event with automatic secret redaction."""
        event_id = str(uuid.uuid4())
        safe_payload = redact_secrets(json.dumps(payload))
        now_utc = datetime.now(timezone.utc).isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO events (id, session_id, correlation_id, event_type, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, session_id, correlation_id, event_type, safe_payload, now_utc),
            )
        return event_id

    def list_events_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "correlation_id": r["correlation_id"],
                    "event_type": r["event_type"],
                    "payload": json.loads(r["payload"]),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
