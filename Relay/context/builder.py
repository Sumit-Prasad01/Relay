"""Unified context builder with token budgeting and precedence ordering (Section 10.3)."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Relay.context.instructions import InstructionLoader
from Relay.context.project import ProjectDiscovery, ProjectInfo
from Relay.context.tokenizer import TokenBudget, TokenEstimator
from Relay.providers.base import ModelMessage


class ContextBuilder:
    """Assembles the final context payload for a turn adhering to token budgets."""

    def __init__(self, workspace_root: Path, budget: Optional[TokenBudget] = None):
        self.workspace_root = workspace_root.resolve()
        self.budget = budget or TokenBudget()
        self.discovery = ProjectDiscovery(self.workspace_root)
        self.instruction_loader = InstructionLoader(self.workspace_root)

    def build_system_prompt(self, base_system_prompt: str) -> str:
        """Compose system prompt with project instructions and environment details."""
        parts = [base_system_prompt.strip()]

        # 1. Project instructions (AGENTS.md)
        instructions = self.instruction_loader.load_instructions()
        if instructions:
            parts.append(instructions)

        # 2. Environment metadata
        info = self.discovery.discover()
        env_lines = [
            "<environment>",
            f"workspace: {self.workspace_root}",
            f"time: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}",
        ]
        if info.git_branch:
            env_lines.append(f"git_branch: {info.git_branch}")
        if info.languages:
            env_lines.append(f"languages: {', '.join(info.languages)}")
        if info.test_commands:
            env_lines.append(f"test_commands: {', '.join(info.test_commands)}")
        env_lines.append("</environment>")

        parts.append("\n".join(env_lines))
        return "\n\n".join(parts)

    def fit_messages(
        self,
        system_prompt: str,
        messages: List[ModelMessage],
        max_prompt_tokens: Optional[int] = None,
    ) -> List[ModelMessage]:
        """Trim messages to strictly fit within the token budget."""
        budget = max_prompt_tokens or self.budget.max_prompt_budget
        system_tokens = TokenEstimator.estimate_text(system_prompt)
        available = budget - system_tokens

        # Always keep system prompt
        fit: List[ModelMessage] = [ModelMessage(role="system", content=system_prompt)]

        # Walk backwards from most recent message
        accumulated: List[ModelMessage] = []
        tokens_spent = 0

        for m in reversed(messages):
            cost = TokenEstimator.estimate_text(m.content) + 4
            if tokens_spent + cost > available and accumulated:
                break
            accumulated.append(m)
            tokens_spent += cost

        fit.extend(reversed(accumulated))
        return fit
