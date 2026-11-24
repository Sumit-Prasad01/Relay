"""Project discovery, technology stack detection, and manifest analysis (Section 10.1)."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from Relay.context.ignore import IgnoreRules


@dataclass
class ProjectInfo:
    workspace_root: Path
    is_git: bool = False
    git_branch: Optional[str] = None
    git_dirty_files: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    manifests: List[str] = field(default_factory=list)
    test_commands: List[str] = field(default_factory=list)
    lint_commands: List[str] = field(default_factory=list)
    instruction_files: List[str] = field(default_factory=list)


MANIFEST_DETECT_MAP: Dict[str, Dict[str, Any]] = {
    "pyproject.toml": {"language": "Python", "test": "python -m pytest", "lint": "ruff check ."},
    "requirements.txt": {"language": "Python", "test": "python -m pytest", "lint": "ruff check ."},
    "package.json": {"language": "JavaScript/TypeScript", "test": "npm test", "lint": "npm run lint"},
    "Cargo.toml": {"language": "Rust", "test": "cargo test", "lint": "cargo clippy"},
    "go.mod": {"language": "Go", "test": "go test ./...", "lint": "golangci-lint run"},
    "pom.xml": {"language": "Java", "test": "mvn test", "lint": "mvn checkstyle:check"},
    "build.gradle": {"language": "Java/Kotlin", "test": "gradle test", "lint": "gradle check"},
}


class ProjectDiscovery:
    """Inspects a repository without recursively loading entire file contents into memory."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.ignore_rules = IgnoreRules(self.workspace_root)

    def discover(self) -> ProjectInfo:
        info = ProjectInfo(workspace_root=self.workspace_root)
        self._detect_git(info)
        self._detect_manifests_and_commands(info)
        self._detect_instruction_files(info)
        return info

    def _detect_git(self, info: ProjectInfo) -> None:
        git_dir = self.workspace_root / ".git"
        if not git_dir.is_dir():
            return
        info.is_git = True
        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            info.git_branch = branch or "(detached)"

            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.splitlines()
            info.git_dirty_files = [line[3:].strip() for line in status if len(line) > 3][:20]
        except Exception:
            pass

    def _detect_manifests_and_commands(self, info: ProjectInfo) -> None:
        langs: set[str] = set()
        tests: set[str] = set()
        lints: set[str] = set()

        for manifest_name, meta in MANIFEST_DETECT_MAP.items():
            candidate = self.workspace_root / manifest_name
            if candidate.is_file():
                info.manifests.append(manifest_name)
                langs.add(meta["language"])
                tests.add(meta["test"])
                lints.add(meta["lint"])

        info.languages = sorted(langs)
        info.test_commands = sorted(tests)
        info.lint_commands = sorted(lints)

    def _detect_instruction_files(self, info: ProjectInfo) -> None:
        candidates = ["AGENTS.md", "README.md", "CONTRIBUTING.md", "ARCHITECTURE.md"]
        for c in candidates:
            if (self.workspace_root / c).is_file():
                info.instruction_files.append(c)
