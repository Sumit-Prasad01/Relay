"""Stop conditions and safety limit evaluators for agent execution (Section 7.3)."""

from typing import Optional, Tuple
from Relay.agent.state import AgentState
from Relay.config.schemas import AgentConfig


class StopConditionEvaluator:
    """Evaluates whether an active agent loop should terminate."""

    @staticmethod
    def evaluate(
        state: AgentState,
        turn_tool_calls: int,
        elapsed_seconds: float,
        config: AgentConfig,
    ) -> Optional[Tuple[str, str]]:
        """
        Evaluate stop conditions.
        Returns (reason_code, human_message) if execution must stop, else None.
        """
        # 1. User cancellation
        if state.is_cancelled:
            return ("cancelled", "Execution cancelled by user.")

        # 2. Maximum iterations
        if state.iteration_count >= config.max_iterations:
            return (
                "max_iterations",
                f"Reached maximum allowed iterations ({config.max_iterations}).",
            )

        # 3. Maximum tool calls in current turn
        if turn_tool_calls >= config.max_tool_calls:
            return (
                "max_tool_calls",
                f"Exceeded maximum tool calls for this turn ({config.max_tool_calls}).",
            )

        # 4. Task wall-clock timeout
        if elapsed_seconds >= config.task_timeout_seconds:
            return (
                "task_timeout",
                f"Task exceeded execution timeout ({config.task_timeout_seconds}s).",
            )

        # 5. Token budget exceeded
        if state.total_tokens_used >= config.max_context_tokens:
            return (
                "token_limit",
                f"Session token usage ({state.total_tokens_used}) exceeded budget ({config.max_context_tokens}).",
            )

        return None
