from pathlib import Path
import pytest
from Relay.storage.database import Database
from Relay.storage.session_store import SessionStore
from Relay.storage.event_store import EventStore


def test_session_lifecycle(tmp_path):
    db = Database(tmp_path / "sessions.db")
    db.run_migrations()

    store = SessionStore(db)
    session_id = store.create_session(
        workspace=tmp_path,
        provider="groq",
        model="llama-3.3-70b-versatile",
        title="Initial test task",
    )
    assert session_id is not None

    session = store.get_session(session_id)
    assert session is not None
    assert session["title"] == "Initial test task"
    assert session["status"] == "active"

    m1_id = store.append_message(session_id, "user", "Hello, please list files.")
    m2_id = store.append_message(session_id, "assistant", "Sure, scanning workspace.")

    messages = store.get_messages(session_id)
    assert len(messages) == 2
    assert messages[0]["sequence"] == 0
    assert messages[0]["content"] == "Hello, please list files."
    assert messages[1]["sequence"] == 1


def test_event_recording(tmp_path):
    db = Database(tmp_path / "events.db")
    db.run_migrations()

    events = EventStore(db)
    ev_id = events.record_event(
        event_type="tool_execution",
        payload={"tool": "list_files", "args": {"path": "."}},
        session_id="test-session-123",
        correlation_id="turn-1",
    )
    assert ev_id is not None

    records = events.list_events_for_session("test-session-123")
    assert len(records) == 1
    assert records[0]["event_type"] == "tool_execution"
    assert records[0]["payload"]["tool"] == "list_files"
