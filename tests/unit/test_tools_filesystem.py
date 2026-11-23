from pathlib import Path
import pytest
from Relay.tools.filesystem import ListFilesTool, ReadFileTool, WriteFileTool


class MockContext:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root


def test_filesystem_tools(tmp_path):
    ctx = MockContext(tmp_path)

    # 1. Write file
    writer = WriteFileTool()
    res_w = writer.run({"path": "src/hello.txt", "content": "Hello World\nLine 2\nLine 3"}, ctx)
    assert res_w.success is True
    assert (tmp_path / "src" / "hello.txt").is_file()

    # 2. List files
    lister = ListFilesTool()
    res_l = lister.run({"path": "src"}, ctx)
    assert res_l.success is True
    assert "hello.txt" in res_l.content

    # 3. Read file with line numbers
    reader = ReadFileTool()
    res_r = reader.run({"path": "src/hello.txt", "offset": 1, "limit": 2}, ctx)
    assert res_r.success is True
    assert "1 | Hello World" in res_r.content
    assert "2 | Line 2" in res_r.content
