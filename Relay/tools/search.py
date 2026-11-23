"""Code search tool (Section 8.3)."""

from pathlib import Path
from typing import Any, Dict
from Relay.context.search import CodeSearchEngine
from Relay.tools.base import BaseTool, ToolResult


class SearchCodeTool(BaseTool):
    name = "search_code"
    description = "Search codebase for a pattern or keyword using ripgrep with fallback."
    category = "read"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Text or regex to search for"},
            "is_regex": {"type": "boolean", "description": "Treat query as regular expression", "default": False},
            "file_glob": {"type": "string", "description": "Optional file glob filter, e.g. '*.py'"},
            "max_results": {"type": "integer", "description": "Maximum matches to return", "default": 25},
        },
        "required": ["query"],
    }

    def run(self, arguments: Dict[str, Any], context: Any) -> ToolResult:
        workspace_root = Path(getattr(context, "workspace_root", Path.cwd())).resolve()
        engine = CodeSearchEngine(workspace_root)

        matches = engine.search(
            query=arguments["query"],
            is_regex=arguments.get("is_regex", False),
            file_glob=arguments.get("file_glob"),
            max_results=arguments.get("max_results", 25),
        )

        if not matches:
            return ToolResult(content=f"No matches found for '{arguments['query']}'.", success=True)

        lines = []
        for m in matches:
            lines.append(f"{m.path}:{m.line_number}: {m.line_text}")

        return ToolResult(content="\n".join(lines), success=True)
