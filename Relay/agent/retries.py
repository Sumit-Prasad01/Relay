"""Error classification, backoff calculation, and retry policies (Section 7.4)."""

import asyncio
import random
from typing import Any, Callable, Coroutine, Optional, TypeVar
from Relay.utils.errors import AuthenticationError, NetworkTimeoutError, RateLimitError

T = TypeVar("T")


def is_transient_error(e: Exception) -> bool:
    """Determine whether an error is transient and safe to retry with backoff."""
    if isinstance(e, (RateLimitError, NetworkTimeoutError)):
        return True

    # Never retry authentication or permission errors
    if isinstance(e, AuthenticationError):
        return False

    msg = str(e).lower()
    transient_indicators = [
        "rate limit",
        "429",
        "timeout",
        "timed out",
        "502",
        "503",
        "504",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "overloaded",
        "connection reset",
    ]
    return any(ind in msg for ind in transient_indicators)


class RetryPolicy:
    """Configurable exponential backoff retry policy with jitter."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        backoff_factor: float = 2.0,
        max_delay: float = 30.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate exponential delay for a retry attempt with optional jitter."""
        delay = min(self.initial_delay * (self.backoff_factor ** attempt), self.max_delay)
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)
        return round(delay, 3)

    async def execute(
        self,
        fn: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        on_retry: Optional[Callable[[int, float, Exception], None]] = None,
        **kwargs: Any,
    ) -> T:
        """Execute an async function with bounded exponential retry for transient errors."""
        attempt = 0
        while True:
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                if not is_transient_error(e) or attempt >= self.max_retries:
                    raise e

                delay = self.get_delay(attempt)
                if on_retry:
                    on_retry(attempt + 1, delay, e)

                await asyncio.sleep(delay)
                attempt += 1
