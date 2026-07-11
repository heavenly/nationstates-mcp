"""Rate-limit utilities for the NationStates API.

Contains:

* **TokenBucket** — self-imposed rate limit (50 req / 30 s default) plus
  server-returned ``X-Retry-After`` backoff observation.
* **TelegramRateLimiter** — per-client-key timing gate for API telegrams
  (recruitment: 1 per 180 s, non-recruitment: 1 per 30 s).
* **get_shared_bucket** — module-level singleton so all tool calls share
  a single rate limiter.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

DEFAULT_RATE = 50  # requests
DEFAULT_PERIOD = 30.0  # seconds


class TokenBucket:
    """Token-bucket rate limiter — self-throttle + server-header observer.

    The bucket is refilled continuously at ``rate / period`` tokens per
    second.  :meth:`acquire` blocks until at least one token is available.
    """

    def __init__(
        self, rate: int = DEFAULT_RATE, period: float = DEFAULT_PERIOD
    ) -> None:
        self.rate = rate
        self.period = period
        self._tokens = float(rate)
        self._last_refill = time.monotonic()
        self._server_retry_after: float = 0.0
        self._lock = asyncio.Lock()

    # ---- Public API ------------------------------------------------------------

    async def acquire(self) -> None:
        """Block until a token is available.

        Respects both the self-imposed rate limit and any server-requested
        backoff (from ``X-Retry-After`` / ``Retry-After`` headers observed
        by :meth:`on_response`).
        """
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(
                    self.rate, self._tokens + elapsed * (self.rate / self.period)
                )
                self._last_refill = now

                if self._server_retry_after > 0:
                    wait_time = self._server_retry_after
                    self._server_retry_after = 0.0
                elif self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                else:
                    wait_time = (1.0 - self._tokens) * (self.period / self.rate)

            logger.debug("Rate limit: waiting %.2fs", wait_time)
            await asyncio.sleep(wait_time)

    def on_response(self, headers: dict[str, str]) -> None:
        """Inspect response headers for server-side rate-limit directives.

        If ``X-Retry-After`` or ``Retry-After`` is present, store a backoff
        that will be honoured by the next :meth:`acquire` call.
        """
        normalized = {key.lower(): value for key, value in headers.items()}
        retry_after = normalized.get("x-retry-after") or normalized.get("retry-after")
        reset = normalized.get("ratelimit-reset")
        remaining = normalized.get("ratelimit-remaining")
        if retry_after:
            try:
                self._server_retry_after = float(retry_after)
                logger.info(
                    "Server requested backoff of %.1fs",
                    self._server_retry_after,
                )
            except ValueError:
                logger.warning("Unparseable X-Retry-After: %s", retry_after)
        elif remaining == "0" and reset:
            try:
                self._server_retry_after = max(self._server_retry_after, float(reset))
            except ValueError:
                logger.warning("Unparseable RateLimit-Reset: %s", reset)

    @property
    def available_tokens(self) -> float:
        return self._tokens


# ---- Shared singleton ---------------------------------------------------------

_shared_bucket: TokenBucket | None = None
_shared_telegram_limiter: TelegramRateLimiter | None = None


def get_shared_bucket() -> TokenBucket:
    """Return a module-level :class:`TokenBucket` singleton.

    All callers that use this function share the same rate limiter, ensuring
    that concurrent tool calls don't exceed the API's overall rate limit.
    """
    global _shared_bucket
    if _shared_bucket is None:
        _shared_bucket = TokenBucket()
    return _shared_bucket


# ---- Telegram rate limiter ----------------------------------------------------

class _TelegramBucket:
    """Per-client-key tracking of last send time."""

    RECRUITMENT_INTERVAL = 180.0  # seconds
    NON_RECRUITMENT_INTERVAL = 30.0  # seconds

    def __init__(self) -> None:
        self._last_send: dict[bool, float] = {
            True: 0.0,  # recruitment
            False: 0.0,  # non-recruitment
        }
        self._lock = asyncio.Lock()

    async def acquire(self, is_recruitment: bool) -> None:
        """Wait until the minimum interval since the last send has elapsed."""
        interval = (
            self.RECRUITMENT_INTERVAL
            if is_recruitment
            else self.NON_RECRUITMENT_INTERVAL
        )
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_send[is_recruitment]
                if elapsed >= interval:
                    self._last_send[is_recruitment] = now
                    return
                wait = interval - elapsed
            # Sleep outside the lock so other coroutines can check progress
            await asyncio.sleep(wait)


class TelegramRateLimiter:
    """Per-API-client-key rate limiter for telegrams.

    Recruitment telegrams:   1 per 180 seconds per client key.
    Non-recruitment telegrams: 1 per  30 seconds per client key.

    Usage::

        limiter = TelegramRateLimiter()
        await limiter.acquire("my_client_key", is_recruitment=False)
        # ... send telegram ...
        limiter.on_response(response_headers)
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _TelegramBucket] = {}

    async def acquire(
        self, client_key: str, is_recruitment: bool = False
    ) -> None:
        """Wait for the telegram rate limit slot for *client_key*."""
        if client_key not in self._buckets:
            self._buckets[client_key] = _TelegramBucket()
        await self._buckets[client_key].acquire(is_recruitment)

    def on_response(self, headers: dict[str, str]) -> None:
        """Observe response headers for telegram-specific backoff signals.

        Currently a no-op but reserved for future server-side rate-limit
        headers that may apply specifically to telegrams.
        """
        # Reserved for future use
        _ = headers


def get_shared_telegram_limiter() -> TelegramRateLimiter:
    """Return the process-wide telegram limiter shared by all tool calls."""
    global _shared_telegram_limiter
    if _shared_telegram_limiter is None:
        _shared_telegram_limiter = TelegramRateLimiter()
    return _shared_telegram_limiter
