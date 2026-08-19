"""Per-provider rate limiting.

A token bucket sized from the provider's own `RateLimitConfig`, plus tracking of
the quota headers the provider reports back. There is one limiter per provider —
never a shared global one, because providers' limits differ by orders of
magnitude.

The clock and the sleep function are injectable so tests can exercise the
throttling logic deterministically instead of actually waiting.
"""

import asyncio
import time
from typing import Awaitable, Callable, Dict, Optional

from .config import RateLimitConfig
from .errors import RateLimitExceededError

__all__ = ["RateLimiter", "QuotaState"]


class QuotaState:
    """Latest quota figures the provider reported in its response headers."""

    def __init__(self):
        self.limit: Optional[int] = None
        self.remaining: Optional[int] = None
        self.reset: Optional[str] = None
        self.updated_at: Optional[float] = None

    def as_dict(self) -> Dict[str, Optional[object]]:
        return {
            "limit": self.limit,
            "remaining": self.remaining,
            "reset": self.reset,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "QuotaState(limit={0}, remaining={1})".format(self.limit, self.remaining)


class RateLimiter:
    """Token-bucket limiter for a single provider.

    Capacity and refill rate come from `requests_per_hour`; `requests_per_second`
    and `min_interval_seconds` add a short-term ceiling so a burst cannot exhaust
    an hourly quota in a few seconds.
    """

    def __init__(
        self,
        config: RateLimitConfig,
        clock: Optional[Callable[[], float]] = None,
        sleeper: Optional[Callable[[float], Awaitable[None]]] = None,
    ):
        self.config = config
        self._clock = clock or time.monotonic
        self._sleep = sleeper or asyncio.sleep
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self.quota = QuotaState()

        if config.requests_per_hour:
            self._capacity = float(config.requests_per_hour)
            self._refill_per_second = config.requests_per_hour / 3600.0
        else:
            self._capacity = 0.0
            self._refill_per_second = 0.0
        self._tokens = self._capacity
        self._last_refill = self._clock()
        self._last_request_at: Optional[float] = None
        #: Number of times a caller had to wait. Reported in ingestion stats.
        self.throttled_count = 0

    # -- token bucket ------------------------------------------------------
    def _refill(self) -> None:
        if self._refill_per_second <= 0:
            return
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        self._last_refill = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)

    def _delay_until_token(self) -> float:
        if self._refill_per_second <= 0:
            return 0.0
        if self._tokens >= 1.0:
            return 0.0
        return (1.0 - self._tokens) / self._refill_per_second

    def _delay_until_interval(self) -> float:
        interval = self.config.min_interval_seconds
        if interval <= 0 or self._last_request_at is None:
            return 0.0
        elapsed = self._clock() - self._last_request_at
        return max(0.0, interval - elapsed)

    def next_delay(self) -> float:
        """Seconds a caller would have to wait right now. Does not consume."""
        self._refill()
        return max(self._delay_until_token(), self._delay_until_interval())

    async def acquire(self) -> float:
        """Wait until a request is permitted, then consume one token.

        Returns how long the caller was delayed, so the HTTP layer can log it.
        """
        async with self._lock:
            self._refill()
            delay = max(self._delay_until_token(), self._delay_until_interval())
            if delay > 0:
                self.throttled_count += 1
                await self._sleep(delay)
                self._refill()
            if self._capacity > 0:
                self._tokens = max(0.0, self._tokens - 1.0)
            self._last_request_at = self._clock()
            return delay

    # -- provider-reported quota ------------------------------------------
    def observe_headers(self, headers) -> None:
        """Record the quota the provider reported, and honour a low threshold.

        Providers are the authority on their own remaining quota; our token
        bucket is only an estimate. When the provider says we are nearly out, we
        believe it over our own arithmetic.
        """
        config = self.config
        if headers is None:
            return

        def _get(name: Optional[str]) -> Optional[str]:
            if not name:
                return None
            try:
                return headers.get(name)
            except AttributeError:  # pragma: no cover - defensive
                return None

        limit = _get(config.limit_header)
        remaining = _get(config.remaining_header)
        reset = _get(config.reset_header)

        if limit is not None:
            try:
                self.quota.limit = int(float(limit))
            except (TypeError, ValueError):
                pass
        if remaining is not None:
            try:
                self.quota.remaining = int(float(remaining))
            except (TypeError, ValueError):
                pass
        if reset is not None:
            self.quota.reset = str(reset)
        self.quota.updated_at = self._clock()

        # Trust the provider's own count over our estimate when it is lower.
        if self.quota.remaining is not None and self._capacity > 0:
            self._tokens = min(self._tokens, float(self.quota.remaining))

    def check_quota(self, source_name: Optional[str] = None) -> None:
        """Raise before sending if the provider says we are out of quota."""
        remaining = self.quota.remaining
        if remaining is None:
            return
        if remaining <= self.config.low_quota_threshold:
            raise RateLimitExceededError(
                "provider reports {0} requests remaining (threshold {1}); refusing to "
                "send further requests".format(remaining, self.config.low_quota_threshold),
                source_name=source_name,
            )

    def concurrency_slot(self):
        """Async context manager limiting simultaneous in-flight requests."""
        return self._semaphore
