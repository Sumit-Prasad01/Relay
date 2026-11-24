"""Tests for CLI sessions management: show, export, delete (Section 12)."""

from pathlib import Path
from typer.testing import CliRunner

from Relay.app import create_app_context
from Relay.cli.app import app

runner = CliRunner()


def test_cli_sessions_lifecycle(tmp_path: Path):
    app_ctx = create_app_context(workspace_root=tmp_path)
    sess_id = app_ctx.session_store.create_session(
        workspace=tmp_path,
        provider="groq",
        model="llama-3.3-70b-versatile",
        title="Test CLI Session",
    )
    app_ctx.session_store.append_message(sess_id, "user", "Explain recursion")
    app_ctx.session_store.append_message(sess_id, "assistant", "Recursion is when a function calls itself.")

    # 1. sessions show
    res_show = runner.invoke(app, ["sessions", "show", sess_id[:8], "--workspace", str(tmp_path)])
    assert res_show.exit_code == 0
    assert "Test CLI Session" in res_show.output
    assert "Explain recursion" in res_show.output

    # 2. sessions export markdown
    res_export = runner.invoke(app, ["sessions", "export", sess_id[:8], "--format", "markdown", "--workspace", str(tmp_path)])
    assert res_export.exit_code == 0
    assert "# Session Transcript: Test CLI Session" in res_export.output
    assert "Recursion is when a function calls itself." in res_export.output

    # 3. sessions export json
    res_export_json = runner.invoke(app, ["sessions", "export", sess_id[:8], "--format", "json", "--workspace", str(tmp_path)])
    assert res_export_json.exit_code == 0
    assert '"title": "Test CLI Session"' in res_export_json.output

    # 4. sessions delete
    res_del = runner.invoke(app, ["sessions", "delete", sess_id[:8], "--workspace", str(tmp_path)])
    assert res_del.exit_code == 0
    assert "Deleted session" in res_del.output

    # Confirm deletion
    deleted = app_ctx.session_store.get_session(sess_id)
    assert deleted is None
