"""Evaluation metrics tracker for agent benchmark tasks (Section 16.4)."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvaluationMetrics:
    """Tracks performance and safety metrics during benchmark evaluations."""

    tasks_attempted: int = 0
    tasks_completed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    correct_tool_selections: int = 0
    invalid_tool_calls: int = 0
    unsafe_actions_prevented: int = 0
    human_approvals_requested: int = 0
    durations_ms: List[int] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    recovery_attempts: int = 0
    recoveries_succeeded: int = 0

    @property
    def completion_rate(self) -> float:
        if self.tasks_attempted == 0:
            return 0.0
        return round((self.tasks_completed / self.tasks_attempted) * 100, 2)

    @property
    def test_pass_rate(self) -> float:
        total = self.tests_passed + self.tests_failed
        if total == 0:
            return 100.0
        return round((self.tests_passed / total) * 100, 2)

    @property
    def average_duration_ms(self) -> float:
        if not self.durations_ms:
            return 0.0
        return round(sum(self.durations_ms) / len(self.durations_ms), 2)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def record_task(
        self,
        completed: bool,
        duration_ms: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        self.tasks_attempted += 1
        if completed:
            self.tasks_completed += 1
        self.durations_ms.append(duration_ms)
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens

    def record_tool_call(self, valid: bool, correct: bool) -> None:
        if valid:
            if correct:
                self.correct_tool_selections += 1
        else:
            self.invalid_tool_calls += 1

    def record_safety_event(self, prevented_unsafe: bool = True) -> None:
        if prevented_unsafe:
            self.unsafe_actions_prevented += 1

    def record_recovery(self, succeeded: bool) -> None:
        self.recovery_attempts += 1
        if succeeded:
            self.recoveries_succeeded += 1

    def summary(self) -> Dict[str, Any]:
        return {
            "tasks_attempted": self.tasks_attempted,
            "tasks_completed": self.tasks_completed,
            "completion_rate_pct": self.completion_rate,
            "tests_passed": self.tests_passed,
            "test_pass_rate_pct": self.test_pass_rate,
            "correct_tool_selections": self.correct_tool_selections,
            "invalid_tool_calls": self.invalid_tool_calls,
            "unsafe_actions_prevented": self.unsafe_actions_prevented,
            "human_approvals_requested": self.human_approvals_requested,
            "average_duration_ms": self.average_duration_ms,
            "total_tokens": self.total_tokens,
            "recovery_success_rate_pct": (
                round((self.recoveries_succeeded / self.recovery_attempts) * 100, 2)
                if self.recovery_attempts > 0
                else 100.0
            ),
        }
