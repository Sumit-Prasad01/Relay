"""Relevance ranking for selective context selection (Section 10.4)."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from Relay.context.ignore import IgnoreRules


@dataclass
class RankedFile:
    path: str
    score: float
    reasons: List[str]


class RelevanceRanker:
    """Ranks workspace files by relevance to user query and active work."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.ignore_rules = IgnoreRules(self.workspace_root)

    def rank(
        self,
        user_query: str,
        recent_files: Optional[List[str]] = None,
        git_dirty_files: Optional[List[str]] = None,
        max_files: int = 10,
    ) -> List[RankedFile]:
        scores: Dict[str, float] = {}
        reasons: Dict[str, List[str]] = {}

        # 1. Explicit file paths mentioned in user query
        tokens = set(re.findall(r"[\w\./\-]+\.[a-zA-Z0-9]+", user_query))
        for token in tokens:
            candidate = self.workspace_root / token
            if candidate.is_file() and not self.ignore_rules.is_ignored(candidate):
                rel = candidate.relative_to(self.workspace_root).as_posix()
                scores[rel] = scores.get(rel, 0.0) + 10.0
                reasons.setdefault(rel, []).append("explicitly mentioned in query")

        # 2. Files referenced in recent tool calls
        for rf in recent_files or []:
            candidate = self.workspace_root / rf
            if candidate.is_file() and not self.ignore_rules.is_ignored(candidate):
                rel = candidate.relative_to(self.workspace_root).as_posix()
                scores[rel] = scores.get(rel, 0.0) + 5.0
                reasons.setdefault(rel, []).append("recently touched in turn")

        # 3. Active git changes
        for gf in git_dirty_files or []:
            candidate = self.workspace_root / gf
            if candidate.is_file() and not self.ignore_rules.is_ignored(candidate):
                rel = candidate.relative_to(self.workspace_root).as_posix()
                scores[rel] = scores.get(rel, 0.0) + 3.0
                reasons.setdefault(rel, []).append("modified in working tree")

        # 4. Keyword matching against file names
        query_words = {w.lower() for w in re.findall(r"[a-zA-Z0-9_]{3,}", user_query)}
        for p in self.workspace_root.rglob("*"):
            if not p.is_file() or self.ignore_rules.is_ignored(p):
                continue
            name_lower = p.name.lower()
            rel = p.relative_to(self.workspace_root).as_posix()
            matched_words = [w for w in query_words if w in name_lower]
            if matched_words:
                scores[rel] = scores.get(rel, 0.0) + 2.0 * len(matched_words)
                reasons.setdefault(rel, []).append(f"name matches {', '.join(matched_words)}")

        ranked = [
            RankedFile(path=path, score=score, reasons=reasons.get(path, []))
            for path, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        ]
        return ranked[:max_files]
