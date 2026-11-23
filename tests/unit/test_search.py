from pathlib import Path
import pytest
from Relay.context.search import CodeSearchEngine


def test_python_code_search(tmp_path):
    # Setup source files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    code_file = src_dir / "calc.py"
    code_file.write_text(
        "def add(a, b):\n"
        "    # Add two numbers\n"
        "    return a + b\n\n"
        "def multiply(a, b):\n"
        "    return a * b\n",
        encoding="utf-8",
    )

    searcher = CodeSearchEngine(tmp_path)

    # Literal search
    matches = searcher.search("def add", is_regex=False)
    assert len(matches) == 1
    assert matches[0].path == "src/calc.py"
    assert matches[0].line_number == 1
    assert "def add(a, b):" in matches[0].line_text

    # Regex search
    regex_matches = searcher.search(r"def\s+\w+\(a,\s*b\):", is_regex=True)
    assert len(regex_matches) == 2
