import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry(
    fn: Callable[[], T],
    *,
    attempts: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    retry_on: Callable[[Exception], bool] = lambda _: True,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> T:
    """Call fn with exponential backoff + jitter. Re-raises the last error."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — caller decides via retry_on
            if attempt >= attempts or not retry_on(exc):
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
            if on_retry:
                on_retry(attempt, exc, delay)
            time.sleep(delay)
    raise RuntimeError("unreachable")
