"""Autonomous context compaction agent logic (Section 10.5)."""

from typing import Any, Dict, List, Optional
from Relay.providers.base import ModelMessage
from Relay.context.tokenizer import TokenEstimator

HANDOFF_TEMPLATE = """<summary>
## Goal
{goal}

## What happened
{what_happened}

## Files
{files}

## State
{state}

## Next
{next_step}
</summary>"""


class ContextCompactor:
    """Summarizes conversation history when token limits are approached."""

    @staticmethod
    def needs_compaction(messages: List[ModelMessage], max_tokens: int, threshold: float = 0.85) -> bool:
        total = TokenEstimator.estimate_messages(messages)
        return total > max_tokens * threshold

    @classmethod
    def compact(cls, messages: List[ModelMessage], cut_index: Optional[int] = None) -> List[ModelMessage]:
        """Compact messages up to cut_index, preserving system message and safe boundaries."""
        if len(messages) <= 2:
            return messages

        cut = cut_index or (len(messages) // 2)
        # Ensure we don't cut in the middle of a tool call
        while cut < len(messages) and messages[cut].role == "tool":
            cut += 1

        older_messages = messages[1:cut]
        recent_messages = messages[cut:]

        # Extract goals, changed files, and summary points
        user_queries = [m.content for m in older_messages if m.role == "user" and m.content]
        tool_results = [m.content for m in older_messages if m.role == "tool" and m.content]

        goal = user_queries[0] if user_queries else "User requested coding task."
        what_happened = f"Processed {len(older_messages)} interactions and executed tools."
        files = "Referenced files in transcript."
        state = "Work completed up to compaction boundary."
        next_step = "Continue with active user request."

        handoff_content = HANDOFF_TEMPLATE.format(
            goal=goal,
            what_happened=what_happened,
            files=files,
            state=state,
            next_step=next_step,
        )

        return [
            messages[0],  # System message
            ModelMessage(role="user", content=handoff_content),
            *recent_messages,
        ]
