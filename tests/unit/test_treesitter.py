from pathlib import Path
import pytest
from Relay.context.treesitter import CodeStructureExtractor


def test_python_structure_extraction(tmp_path):
    file_path = tmp_path / "module.py"
    file_path.write_text(
        "import os\n"
        "from typing import List\n\n"
        "class Calculator:\n"
        "    '''Main calculator class.'''\n"
        "    pass\n\n"
        "def compute(val: int) -> int:\n"
        "    '''Compute value.'''\n"
        "    return val * 2\n",
        encoding="utf-8",
    )

    structure = CodeStructureExtractor.extract_python(file_path, relative_to=tmp_path)
    assert structure is not None
    assert structure.path == "module.py"
    assert len(structure.classes) == 1
    assert structure.classes[0].name == "Calculator"
    assert structure.classes[0].docstring == "Main calculator class."

    assert len(structure.functions) == 1
    assert structure.functions[0].name == "compute"
    assert structure.functions[0].docstring == "Compute value."

    assert len(structure.imports) == 2
