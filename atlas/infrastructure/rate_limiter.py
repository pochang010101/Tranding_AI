"""In-memory rate limiter for external API calls.

Uses a sliding-window counter keyed by an arbitrary string (IP, session ID,
endpoint name, etc.).  Thread-safe via a threading.Lock; suitable for a
single-process Streamlit deployment.  For multi-process deployments, replace
the in-memory store with Redis.

Usage::

    limiter = RateLimiter()

    # Allow at most 10 calls per 60-second window for the TWSE MIS endpoint
    if not limiter.check("twse_mis", max_requests=10, window_seconds=60):
        raise RuntimeError("Rate limit exceeded")
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Sliding-window rate limiter.

    Each key maintains a deque of timestamps for recent requests.  On every
    ``check`` call, expired timestamps (older than *window_seconds*) are
    pruned before the count is evaluated.
    """

    def __init__(self) -> None:
        # key -> deque of monotonic timestamps
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Return True if the request is allowed; False if rate-limited.

        Records the current timestamp when the request is allowed.

        Args:
            key: Identifier for the rate-limit bucket (e.g. ``"twse_mis"``).
            max_requests: Maximum number of allowed requests inside the window.
            window_seconds: Sliding window length in seconds.
        """
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            dq = self._windows[key]

            # Remove timestamps outside the current window
            while dq and dq[0] <= cutoff:
                dq.popleft()

            if len(dq) >= max_requests:
                return False

            dq.append(now)
            return True

    def reset(self, key: str) -> None:
        """Clear all recorded timestamps for *key* (useful in tests)."""
        with self._lock:
            self._windows[key].clear()

    def remaining(self, key: str, max_requests: int, window_seconds: int) -> int:
        """Return how many more requests are allowed in the current window."""
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            dq = self._windows[key]
            current = sum(1 for ts in dq if ts > cutoff)
            return max(0, max_requests - current)


# Module-level singleton — import and use directly for simple cases.
default_limiter = RateLimiter()
