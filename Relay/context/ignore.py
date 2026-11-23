"""Ignore rules engine respecting .gitignore, .relayignore, and standard defaults (Section 8.2)."""

import fnmatch
from pathlib import Path
from typing import List, Set

DEFAULT_IGNORE_PATTERNS = [
    # VCS & environments
    ".git",
    ".git/*",
    ".venv",
    ".venv/*",
    "venv",
    "venv/*",
    "env",
    "env/*",
    # Dependencies & caches
    "node_modules",
    "node_modules/*",
    "__pycache__",
    "__pycache__/*",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".pytest_cache",
    ".pytest_cache/*",
    ".ruff_cache",
    ".ruff_cache/*",
    ".mypy_cache",
    ".mypy_cache/*",
    # Build artifacts
    "dist",
    "dist/*",
    "build",
    "build/*",
    "*.egg-info",
    "*.egg-info/*",
    "target",
    "target/*",
    # IDE & OS files
    ".idea",
    ".idea/*",
    ".vscode",
    ".vscode/*",
    ".DS_Store",
    "Thumbs.db",
    # Secrets & local states
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
]


class IgnoreRules:
    """Evaluates whether paths should be skipped during repository scanning and search."""

    def __init__(self, workspace_root: Path, custom_ignore_file: str = ".relayignore"):
        self.workspace_root = workspace_root.resolve()
        self.patterns: List[str] = list(DEFAULT_IGNORE_PATTERNS)
        self._load_file(self.workspace_root / ".gitignore")
        self._load_file(self.workspace_root / custom_ignore_file)

    def _load_file(self, path: Path) -> None:
        if not path.is_file():
            return
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # Normalize gitignore pattern
                    pattern = line.rstrip("/")
                    self.patterns.append(pattern)
                    self.patterns.append(f"{pattern}/*")
        except Exception:
            pass

    def is_ignored(self, path: Path) -> bool:
        """Check if path is ignored relative to the workspace root."""
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(self.workspace_root):
                return True
            rel_path = resolved.relative_to(self.workspace_root).as_posix()
        except Exception:
            return True

        parts = rel_path.split("/")
        for pattern in self.patterns:
            clean_pat = pattern.rstrip("/*")
            # Check individual directory parts (e.g., node_modules or .venv anywhere in path)
            if clean_pat in parts:
                return True
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            if fnmatch.fnmatch(resolved.name, pattern):
                return True

        return False
