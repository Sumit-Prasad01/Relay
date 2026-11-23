"""Command risk classification and quote-aware parser (Section 9.2)."""

import fnmatch
from enum import Enum
from typing import List, Tuple


class CommandRisk(Enum):
    READ_ONLY = "read_only"
    MUTATION = "mutation"
    NETWORK = "network"
    DESTRUCTIVE = "destructive"
    PRIVILEGED = "privileged"
    UNKNOWN = "unknown"


READ_ONLY_PATTERNS = [
    "ls*", "dir*", "pwd", "cd *", "echo *", "sort*", "uniq*", "cut *",
    "basename *", "dirname *", "date*", "env", "cat *", "head *", "tail *",
    "wc *", "file *", "which *", "where *", "grep *", "rg *", "find *",
    "tree*", "type *", "git status*", "git diff*", "git log*", "git show*",
    "git ls-files*", "python --version", "pytest --collect-only*", "node --version",
]

MUTATION_PATTERNS = [
    "pytest*", "python -m pytest*", "npm test*", "cargo test*", "go test*",
    "ruff check*", "ruff format*", "eslint*", "black*", "prettier*",
]

NETWORK_PATTERNS = [
    "curl *", "wget *", "pip install*", "npm install*", "npm add*", "cargo add*",
    "git push*", "git fetch*", "git pull*", "git clone*", "ssh *",
]

DESTRUCTIVE_PATTERNS = [
    "rm *", "del *", "rmdir *", "git reset*", "git clean*", "drop database*",
    "mkfs*", "dd if=*", "format *",
]

PRIVILEGED_PATTERNS = [
    "sudo *", "su *", "chmod *", "chown *", "systemctl *", "service *",
]


class CommandPolicy:
    """Classifies terminal commands into security risk tiers."""

    @classmethod
    def split_command(cls, command: str) -> List[str]:
        """Split a compound command on pipes, semicolons, and & without breaking inside quotes."""
        parts, current, quote = [], [], None
        index = 0
        while index < len(command):
            char = command[index]
            if quote:
                current.append(char)
                if char == quote:
                    quote = None
            elif char == "\\":
                current.append(char)
                index += 1
                if index < len(command):
                    current.append(command[index])
            elif char in "\"'":
                quote = char
                current.append(char)
            elif char in "&|;":
                parts.append("".join(current))
                current = []
                while index + 1 < len(command) and command[index + 1] in "&|":
                    index += 1
            else:
                current.append(char)
            index += 1

        parts.append("".join(current))
        return [part.strip() for part in parts if part.strip()]

    @classmethod
    def classify_single(cls, part: str) -> CommandRisk:
        clean = part.strip()
        for pattern in PRIVILEGED_PATTERNS:
            if fnmatch.fnmatch(clean, pattern):
                return CommandRisk.PRIVILEGED
        for pattern in DESTRUCTIVE_PATTERNS:
            if fnmatch.fnmatch(clean, pattern):
                return CommandRisk.DESTRUCTIVE
        for pattern in NETWORK_PATTERNS:
            if fnmatch.fnmatch(clean, pattern):
                return CommandRisk.NETWORK
        for pattern in READ_ONLY_PATTERNS:
            if fnmatch.fnmatch(clean, pattern):
                return CommandRisk.READ_ONLY
        for pattern in MUTATION_PATTERNS:
            if fnmatch.fnmatch(clean, pattern):
                return CommandRisk.MUTATION
        return CommandRisk.UNKNOWN

    @classmethod
    def classify(cls, command: str) -> Tuple[CommandRisk, List[str]]:
        """Classify a compound command; the highest risk wins."""
        parts = cls.split_command(command)
        if not parts:
            return CommandRisk.READ_ONLY, []

        risks = [cls.classify_single(p) for p in parts]
        risk_priority = [
            CommandRisk.PRIVILEGED,
            CommandRisk.DESTRUCTIVE,
            CommandRisk.NETWORK,
            CommandRisk.UNKNOWN,
            CommandRisk.MUTATION,
            CommandRisk.READ_ONLY,
        ]

        for priority in risk_priority:
            if priority in risks:
                return priority, parts

        return CommandRisk.UNKNOWN, parts
