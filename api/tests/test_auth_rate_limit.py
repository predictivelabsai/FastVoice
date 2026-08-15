from unittest.mock import AsyncMock

import pytest

from web.auth_rate_limit import attempt_allowed


@pytest.mark.asyncio
async def test_auth_attempt_limit_counts_with_expiry():
    store = AsyncMock()
    store.incr.side_effect = [1, 2, 3]

    assert await attempt_allowed(
        "User@example.com", "login", limit=2, window_seconds=60, store=store
    )
    assert await attempt_allowed(
        "user@example.com", "login", limit=2, window_seconds=60, store=store
    )
    assert not await attempt_allowed(
        "user@example.com", "login", limit=2, window_seconds=60, store=store
    )
    store.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_auth_attempt_limit_fails_closed_when_redis_is_unavailable():
    store = AsyncMock()
    store.incr.side_effect = ConnectionError("redis unavailable")

    assert not await attempt_allowed(
        "user@example.com", "login", limit=2, window_seconds=60, store=store
    )
