"""Custom agent runtime package for Relay (Section 7)."""

from Relay.agent.events import AgentEvent, AgentEventType
from Relay.agent.loop import AgentLoop
from Relay.agent.retries import RetryPolicy
from Relay.agent.runtime import AgentRuntime
from Relay.agent.state import AgentState
from Relay.agent.stop_conditions import StopConditionEvaluator


def main():
    """CLI entrypoint compatibility wrapper."""
    from Relay.cli.app import app
    app()


__all__ = [
    "AgentEvent",
    "AgentEventType",
    "AgentLoop",
    "AgentRuntime",
    "AgentState",
    "RetryPolicy",
    "StopConditionEvaluator",
    "main",
]
