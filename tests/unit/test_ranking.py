from pathlib import Path
import pytest
from Relay.context.ranking import RelevanceRanker


def test_relevance_ranking(tmp_path):
    (tmp_path / "auth.py").write_text("class Authenticator: pass", encoding="utf-8")
    (tmp_path / "database.py").write_text("class Database: pass", encoding="utf-8")
    (tmp_path / "utils.py").write_text("def helper(): pass", encoding="utf-8")

    ranker = RelevanceRanker(tmp_path)

    # 1. Query explicitly mentions auth.py
    ranked = ranker.rank("Please refactor auth.py to use bcrypt", git_dirty_files=["database.py"])
    assert len(ranked) >= 2
    assert ranked[0].path == "auth.py"
    assert any("explicitly mentioned" in r for r in ranked[0].reasons)
    assert ranked[1].path == "database.py"
    assert any("modified in working tree" in r for r in ranked[1].reasons)
