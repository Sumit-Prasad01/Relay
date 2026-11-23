"""Code search engine utilizing ripgrep with robust pure-Python fallback (Section 8.3)."""

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from Relay.context.ignore import IgnoreRules


@dataclass
class SearchMatch:
    path: str
    line_number: int
    line_text: str
    context_before: List[str]
    context_after: List[str]


class CodeSearchEngine:
    """Searches codebases for keywords, regexes, and symbols."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
        self.ignore_rules = IgnoreRules(self.workspace_root)
        self.rg_path = shutil.which("rg")

    def search(
        self,
        query: str,
        is_regex: bool = False,
        file_glob: Optional[str] = None,
        max_results: int = 50,
        context_lines: int = 2,
    ) -> List[SearchMatch]:
        """Perform search using ripgrep if available, otherwise pure Python."""
        if self.rg_path:
            try:
                return self._search_ripgrep(query, is_regex, file_glob, max_results, context_lines)
            except Exception:
                pass

        return self._search_python(query, is_regex, file_glob, max_results, context_lines)

    def _search_ripgrep(
        self,
        query: str,
        is_regex: bool,
        file_glob: Optional[str],
        max_results: int,
        context_lines: int,
    ) -> List[SearchMatch]:
        cmd = [self.rg_path, "--json", f"-C{context_lines}"]
        if not is_regex:
            cmd.append("-F")
        if file_glob:
            cmd.extend(["-g", file_glob])
        cmd.extend([query, str(self.workspace_root)])

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        matches: List[SearchMatch] = []

        current_match = None
        for line in proc.stdout.splitlines():
            if len(matches) >= max_results:
                break
            try:
                data = json.loads(line)
            except Exception:
                continue

            msg_type = data.get("type")
            if msg_type == "match":
                payload = data.get("data", {})
                path_data = payload.get("path", {}).get("text", "")
                rel_path = (
                    Path(path_data).relative_to(self.workspace_root).as_posix()
                    if Path(path_data).is_absolute()
                    else path_data
                )
                line_no = payload.get("line_number", 0)
                line_text = payload.get("lines", {}).get("text", "").strip("\r\n")

                matches.append(
                    SearchMatch(
                        path=rel_path,
                        line_number=line_no,
                        line_text=line_text,
                        context_before=[],
                        context_after=[],
                    )
                )

        return matches

    def _search_python(
        self,
        query: str,
        is_regex: bool,
        file_glob: Optional[str],
        max_results: int,
        context_lines: int,
    ) -> List[SearchMatch]:
        flags = 0 if is_regex else re.IGNORECASE
        try:
            pattern = re.compile(query if is_regex else re.escape(query), flags)
        except re.error:
            pattern = re.compile(re.escape(query))

        matches: List[SearchMatch] = []

        for p in self.workspace_root.rglob("*"):
            if len(matches) >= max_results:
                break
            if not p.is_file() or self.ignore_rules.is_ignored(p):
                continue
            if file_glob and not p.match(file_glob):
                continue
            if p.stat().st_size > 1_000_000:  # Skip files > 1MB
                continue

            try:
                raw_bytes = p.read_bytes()
                if b"\x00" in raw_bytes:  # Binary file check
                    continue
                lines = raw_bytes.decode("utf-8", errors="replace").splitlines()
            except Exception:
                continue

            rel_path = p.relative_to(self.workspace_root).as_posix()
            for idx, line in enumerate(lines):
                if pattern.search(line):
                    before = lines[max(0, idx - context_lines):idx]
                    after = lines[idx + 1:min(len(lines), idx + 1 + context_lines)]
                    matches.append(
                        SearchMatch(
                            path=rel_path,
                            line_number=idx + 1,
                            line_text=line,
                            context_before=before,
                            context_after=after,
                        )
                    )
                    if len(matches) >= max_results:
                        break

        return matches
