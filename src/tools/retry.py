"""Shared retry utility for CareBridge external API calls.

All agents use with_retry() — 3 attempts with exponential backoff
(1s, 2s, 4s). Do not implement custom retry loops.
"""

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_exception: Exception):
        super().__init__(message)
        self.last_exception = last_exception


async def with_retry(
    fn: Callable,
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    **kwargs: Any
) -> Any:
    """Retry an async or sync function with exponential backoff.

    Args:
        fn: The function to retry (async or sync).
        *args: Positional arguments to pass to fn.
        max_attempts: Maximum number of attempts (default 3).
        base_delay: Base delay in seconds (default 1.0). Backoff: 1s, 2s, 4s.
        **kwargs: Keyword arguments to pass to fn.

    Returns:
        The return value of fn on success.

    Raises:
        RetryExhausted: If all attempts fail, wrapping the last exception.
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            if asyncio.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            else:
                return fn(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"Attempt {attempt}/{max_attempts} failed for {fn.__name__}: {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"All {max_attempts} attempts failed for {fn.__name__}: {e}"
                )

    raise RetryExhausted(
        f"Function {fn.__name__} failed after {max_attempts} attempts",
        last_exception=last_exception  # type: ignore
    )
