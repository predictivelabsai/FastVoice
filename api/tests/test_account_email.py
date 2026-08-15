"""Unit tests for FastVoice transactional account emails."""

from types import SimpleNamespace

import pytest

from web import account_email


@pytest.mark.asyncio
async def test_verification_email_uses_configured_public_url(monkeypatch):
    monkeypatch.setenv("POSTMARK_API_TOKEN", "postmark-token")
    monkeypatch.setenv("FROM_EMAIL", "accounts@fastsme.com")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://voice.fastsme.com/")
    sent = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            sent.update(url=url, headers=headers, json=json)
            return SimpleNamespace(is_success=True)

    monkeypatch.setattr(account_email.httpx, "AsyncClient", lambda **_kwargs: Client())

    delivered = await account_email.send_account_link(
        "person@example.com", "verify", "one-time-token"
    )

    assert delivered is True
    assert sent["url"] == "https://api.postmarkapp.com/email"
    assert sent["headers"] == {"X-Postmark-Server-Token": "postmark-token"}
    assert sent["json"]["From"] == "accounts@fastsme.com"
    assert sent["json"]["To"] == "person@example.com"
    assert (
        "https://voice.fastsme.com/auth/verify/one-time-token"
        in sent["json"]["HtmlBody"]
    )


@pytest.mark.asyncio
async def test_account_email_fails_closed_without_postmark_token(monkeypatch):
    monkeypatch.delenv("POSTMARK_API_TOKEN", raising=False)

    delivered = await account_email.send_account_link(
        "person@example.com", "reset", "one-time-token"
    )

    assert delivered is False
