"""Code structure extraction with graceful fallback (Section 10.4)."""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class CodeSymbol:
    name: str
    kind: str  # function, class, import
    line_number: int
    docstring: Optional[str] = None


@dataclass
class FileStructure:
    path: str
    classes: List[CodeSymbol] = field(default_factory=list)
    functions: List[CodeSymbol] = field(default_factory=list)
    imports: List[CodeSymbol] = field(default_factory=list)


class CodeStructureExtractor:
    """Extracts top-level structural symbols from source files."""

    @classmethod
    def extract_python(cls, file_path: Path, relative_to: Optional[Path] = None) -> Optional[FileStructure]:
        if not file_path.is_file() or file_path.suffix != ".py":
            return None

        rel_name = file_path.relative_to(relative_to).as_posix() if relative_to else file_path.name
        structure = FileStructure(path=rel_name)

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except Exception:
            return None

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node)
                structure.classes.append(
                    CodeSymbol(name=node.name, kind="class", line_number=node.lineno, docstring=doc)
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                structure.functions.append(
                    CodeSymbol(name=node.name, kind="function", line_number=node.lineno, docstring=doc)
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    structure.imports.append(
                        CodeSymbol(name=alias.name, kind="import", line_number=node.lineno)
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    structure.imports.append(
                        CodeSymbol(name=f"{mod}.{alias.name}", kind="import", line_number=node.lineno)
                    )

        return structure
