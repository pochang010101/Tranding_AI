"""Unit tests for atlas.infrastructure.rate_limiter."""

import time

import pytest

from atlas.infrastructure.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_limiter() -> RateLimiter:
    return RateLimiter()


# ---------------------------------------------------------------------------
# Normal traffic passes
# ---------------------------------------------------------------------------

def test_single_request_allowed():
    """First request must always be allowed."""
    rl = make_limiter()
    assert rl.check("api", max_requests=5, window_seconds=60) is True


def test_requests_up_to_limit_all_pass():
    """All requests within the quota must be allowed."""
    rl = make_limiter()
    results = [rl.check("api", max_requests=5, window_seconds=60) for _ in range(5)]
    assert all(results)


def test_different_keys_are_independent():
    """Exhausting one key must not affect another."""
    rl = make_limiter()
    for _ in range(3):
        rl.check("key_a", max_requests=3, window_seconds=60)

    # key_a exhausted
    assert rl.check("key_a", max_requests=3, window_seconds=60) is False
    # key_b untouched
    assert rl.check("key_b", max_requests=3, window_seconds=60) is True


# ---------------------------------------------------------------------------
# Over-limit requests are blocked
# ---------------------------------------------------------------------------

def test_request_over_limit_is_blocked():
    """The (max_requests + 1)-th call must be rejected."""
    rl = make_limiter()
    for _ in range(5):
        rl.check("api", max_requests=5, window_seconds=60)

    assert rl.check("api", max_requests=5, window_seconds=60) is False


def test_multiple_over_limit_calls_all_blocked():
    """Subsequent calls after exhaustion must continue to be blocked."""
    rl = make_limiter()
    for _ in range(3):
        rl.check("svc", max_requests=3, window_seconds=60)

    blocked = [rl.check("svc", max_requests=3, window_seconds=60) for _ in range(5)]
    assert all(b is False for b in blocked)


# ---------------------------------------------------------------------------
# Window expiry resets the counter
# ---------------------------------------------------------------------------

def test_window_expiry_allows_new_requests():
    """After the window elapses, the counter must reset and allow new calls."""
    rl = make_limiter()
    # Exhaust a 1-second window
    for _ in range(3):
        rl.check("fast", max_requests=3, window_seconds=1)

    assert rl.check("fast", max_requests=3, window_seconds=1) is False

    time.sleep(1.05)  # wait for window to expire

    # Should be allowed again
    assert rl.check("fast", max_requests=3, window_seconds=1) is True


def test_partial_window_expiry():
    """Only timestamps inside the window count toward the quota."""
    rl = make_limiter()
    # Fill 2 of 3 slots, then wait for them to expire, then add 2 more.
    rl.check("partial", max_requests=3, window_seconds=1)
    rl.check("partial", max_requests=3, window_seconds=1)

    time.sleep(1.05)

    # Old timestamps expired; 2 new slots available
    assert rl.check("partial", max_requests=3, window_seconds=1) is True
    assert rl.check("partial", max_requests=3, window_seconds=1) is True
    # Third slot also free
    assert rl.check("partial", max_requests=3, window_seconds=1) is True
    # Fourth must be blocked (window now has 3)
    assert rl.check("partial", max_requests=3, window_seconds=1) is False


# ---------------------------------------------------------------------------
# reset() helper
# ---------------------------------------------------------------------------

def test_reset_clears_counter():
    """reset() must immediately free the quota for a key."""
    rl = make_limiter()
    for _ in range(5):
        rl.check("r", max_requests=5, window_seconds=60)
    assert rl.check("r", max_requests=5, window_seconds=60) is False

    rl.reset("r")
    assert rl.check("r", max_requests=5, window_seconds=60) is True


# ---------------------------------------------------------------------------
# remaining() helper
# ---------------------------------------------------------------------------

def test_remaining_full_quota():
    rl = make_limiter()
    assert rl.remaining("rem", max_requests=10, window_seconds=60) == 10


def test_remaining_decrements():
    rl = make_limiter()
    rl.check("rem2", max_requests=10, window_seconds=60)
    rl.check("rem2", max_requests=10, window_seconds=60)
    assert rl.remaining("rem2", max_requests=10, window_seconds=60) == 8


def test_remaining_zero_when_exhausted():
    rl = make_limiter()
    for _ in range(5):
        rl.check("rem3", max_requests=5, window_seconds=60)
    assert rl.remaining("rem3", max_requests=5, window_seconds=60) == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_max_requests_one():
    """A quota of 1 must allow the first and block the second."""
    rl = make_limiter()
    assert rl.check("strict", max_requests=1, window_seconds=60) is True
    assert rl.check("strict", max_requests=1, window_seconds=60) is False


def test_large_quota_never_blocks():
    """With a very large quota, 100 rapid calls must all pass."""
    rl = make_limiter()
    results = [rl.check("big", max_requests=10_000, window_seconds=60) for _ in range(100)]
    assert all(results)
