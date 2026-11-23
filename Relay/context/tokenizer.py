"""Token estimation, budgeting, and capacity tracking (Section 10.3)."""

import json
from dataclasses import dataclass
from typing import Any, List


@dataclass
class TokenBudget:
    max_context_tokens: int = 64_000
    reserved_output_tokens: int = 4_096
    reserved_headroom_tokens: int = 2_000

    @property
    def max_prompt_budget(self) -> int:
        return max(1_000, self.max_context_tokens - self.reserved_output_tokens - self.reserved_headroom_tokens)


class TokenEstimator:
    """Fast, reliable token estimation across providers."""

    @staticmethod
    def estimate_text(text: str) -> int:
        """Estimate token count (approx 4 characters per token for code/text)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @classmethod
    def estimate_messages(cls, messages: List[Any]) -> int:
        """Estimate token count for a message array."""
        total = 0
        for m in messages:
            if isinstance(m, dict):
                content = m.get("content") or ""
                total += cls.estimate_text(str(content)) + 4
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    total += cls.estimate_text(fn.get("name", "")) + cls.estimate_text(fn.get("arguments", "")) + 8
            else:
                total += cls.estimate_text(getattr(m, "content", "") or "") + 4
        return total
