import base64
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock

import pytest

from web.suite_auth import redeem_suite_ticket


def _ticket(secret: str, **overrides) -> str:
    payload = {
        "sub": "42",
        "email": "kaljuvee@gmail.com",
        "name": "Julian Kaljuvee",
        "org_id": "7",
        "org_name": "FastSME",
        "role": "owner",
        "aud": "voice",
        "jti": "single-use-ticket",
        "exp": int(time.time()) + 60,
        **overrides,
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


@pytest.mark.asyncio
async def test_suite_ticket_is_verified_and_consumed_once(monkeypatch):
    secret = "suite-test-secret"
    monkeypatch.setenv("FASTOFFICE_SSO_SECRET", secret)
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "kaljuvee@gmail.com")
    store = AsyncMock()
    store.set.return_value = True

    identity = await redeem_suite_ticket(_ticket(secret), replay_store=store)

    assert identity is not None
    assert identity["email"] == "kaljuvee@gmail.com"
    store.set.assert_awaited_once()
    assert store.set.await_args.kwargs["nx"] is True


@pytest.mark.asyncio
async def test_suite_ticket_rejects_replay_wrong_audience_and_expiry(monkeypatch):
    secret = "suite-test-secret"
    monkeypatch.setenv("FASTOFFICE_SSO_SECRET", secret)
    monkeypatch.delenv("GOOGLE_ALLOWED_EMAILS", raising=False)
    store = AsyncMock()
    store.set.return_value = False

    assert await redeem_suite_ticket(_ticket(secret), replay_store=store) is None
    assert (
        await redeem_suite_ticket(_ticket(secret, aud="docs"), replay_store=AsyncMock())
        is None
    )
    assert (
        await redeem_suite_ticket(
            _ticket(secret, exp=int(time.time()) - 1), replay_store=AsyncMock()
        )
        is None
    )


@pytest.mark.asyncio
async def test_suite_ticket_fails_closed_when_replay_store_is_unavailable(monkeypatch):
    secret = "suite-test-secret"
    monkeypatch.setenv("FASTOFFICE_SSO_SECRET", secret)
    monkeypatch.delenv("GOOGLE_ALLOWED_EMAILS", raising=False)
    store = AsyncMock()
    store.set.side_effect = ConnectionError("redis unavailable")

    assert await redeem_suite_ticket(_ticket(secret), replay_store=store) is None
