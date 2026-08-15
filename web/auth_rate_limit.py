"""Redis-backed limits for account authentication attempts."""

from __future__ import annotations

import hashlib

import redis.asyncio as aioredis

from api.constants import REDIS_URL


async def attempt_allowed(
    subject: str,
    action: str,
    *,
    limit: int,
    window_seconds: int,
    store=None,
) -> bool:
    digest = hashlib.sha256(subject.strip().lower().encode()).hexdigest()
    key = f"fastvoice:auth-limit:{action}:{digest}"
    client = store or aioredis.from_url(REDIS_URL, decode_responses=True)
    owns_client = store is None
    try:
        count = int(await client.incr(key))
        if count == 1:
            await client.expire(key, window_seconds)
        return count <= limit
    except Exception:  # noqa: BLE001 - authentication limits fail closed.
        return False
    finally:
        if owns_client:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001 - closing must not weaken fail-closed behavior.
                pass
