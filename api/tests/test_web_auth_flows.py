"""Regression tests for FastVoice browser authentication flows."""

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import web.app as web_app
from web import auth


def _csrf(response) -> str:
    match = re.search(r'name="csrf_token"[^>]+value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def _user(*, verified=False):
    return SimpleNamespace(
        id=7,
        email="person@example.com",
        email_verified=verified,
        password_hash="hashed",
        provider_id="local-user",
        selected_organization_id=1,
    )


def test_login_and_signup_expose_complete_account_paths(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "person@example.com")
    monkeypatch.setenv("FASTOFFICE_SSO_SECRET", "suite-secret")
    client = TestClient(web_app.app)

    login = client.get("/login")
    assert login.status_code == 200
    assert "Continue with Google" in login.text
    assert "Continue with FastSME" in login.text
    assert 'href="/forgot-password"' in login.text
    assert 'href="/signup"' in login.text

    signup = client.get("/signup")
    assert "Confirm password" in signup.text
    assert "verification link" in signup.text
    assert 'minlength="10"' in signup.text


def test_signup_requires_verification_before_creating_a_session(monkeypatch):
    client = TestClient(web_app.app)
    user = _user()
    monkeypatch.setattr(auth, "attempt_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        auth.db_client, "get_user_by_email", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        auth.db_client, "create_user_with_email", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        auth.db_client,
        "issue_user_auth_token",
        AsyncMock(return_value="verification-token"),
    )
    monkeypatch.setattr(auth, "send_account_link", AsyncMock(return_value=True))
    establish = AsyncMock()
    monkeypatch.setattr(auth, "_establish", establish)

    form = client.get("/signup")
    response = client.post(
        "/signup",
        data={
            "name": "Person",
            "email": "person@example.com",
            "password": "a-secure-password",
            "password_confirm": "a-secure-password",
            "csrf_token": _csrf(form),
        },
    )

    assert response.status_code == 200
    assert "Check your email to verify your account" in response.text
    establish.assert_not_awaited()
    auth.db_client.issue_user_auth_token.assert_awaited_once_with(
        user.id, "verify", 24 * 3600
    )
    auth.send_account_link.assert_awaited_once_with(
        "person@example.com", "verify", "verification-token"
    )


def test_verification_link_is_single_use_and_establishes_session(monkeypatch):
    client = TestClient(web_app.app)
    user = _user()
    monkeypatch.setattr(
        auth.db_client, "consume_user_auth_token", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        auth.db_client, "mark_user_email_verified", AsyncMock(return_value=None)
    )
    establish = AsyncMock()
    monkeypatch.setattr(auth, "_establish", establish)

    response = client.get("/auth/verify/one-time-token", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/overview"
    auth.db_client.consume_user_auth_token.assert_awaited_once_with(
        "one-time-token", "verify"
    )
    establish.assert_awaited_once()
    assert establish.await_args.args[1] is user


def test_forgot_and_reset_password_use_generic_single_use_flow(monkeypatch):
    client = TestClient(web_app.app)
    user = _user(verified=True)
    monkeypatch.setattr(auth, "attempt_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        auth.db_client, "get_user_by_email", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        auth.db_client,
        "issue_user_auth_token",
        AsyncMock(return_value="reset-token"),
    )
    monkeypatch.setattr(auth, "send_account_link", AsyncMock(return_value=True))

    forgot = client.get("/forgot-password")
    sent = client.post(
        "/forgot-password",
        data={"email": user.email, "csrf_token": _csrf(forgot)},
    )
    assert "If an account exists, a reset link is on its way" in sent.text
    auth.send_account_link.assert_awaited_once_with(user.email, "reset", "reset-token")

    monkeypatch.setattr(
        auth.db_client, "consume_user_auth_token", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        auth.db_client, "update_user_password", AsyncMock(return_value=None)
    )
    reset = client.get("/auth/reset/reset-token")
    changed = client.post(
        "/auth/reset",
        data={
            "token": "reset-token",
            "password": "a-new-secure-password",
            "password_confirm": "a-new-secure-password",
            "csrf_token": _csrf(reset),
        },
    )
    assert "Your password has been updated" in changed.text
    auth.db_client.consume_user_auth_token.assert_awaited_once_with(
        "reset-token", "reset"
    )


def test_google_oidc_uses_exact_callback_nonce_state_and_safe_return(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "person@example.com")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI", "https://voice.fastsme.com/auth/google/callback"
    )
    client = TestClient(web_app.app)

    start = client.get("/auth/google?next=/recordings", follow_redirects=False)
    assert start.status_code == 303
    query = parse_qs(urlparse(start.headers["location"]).query)
    assert query["redirect_uri"] == ["https://voice.fastsme.com/auth/google/callback"]
    assert query["scope"] == ["openid email profile"]
    assert query["state"][0]
    assert query["nonce"][0]

    response = SimpleNamespace(status_code=200, json=lambda: {"id_token": "id-token"})

    class OAuthClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **_kwargs: OAuthClient())
    monkeypatch.setattr(
        auth.google_id_token,
        "verify_oauth2_token",
        lambda *_args: {
            "sub": "google-user",
            "email": "person@example.com",
            "email_verified": True,
            "nonce": query["nonce"][0],
        },
    )
    user = _user()
    monkeypatch.setattr(
        auth.db_client, "get_user_by_email", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        auth.db_client, "mark_user_email_verified", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(auth, "_establish", AsyncMock(return_value=None))

    callback = client.get(
        "/auth/google/callback",
        params={"code": "code", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert callback.status_code == 303, callback.text
    assert callback.headers["location"] == "/recordings"
    auth.db_client.mark_user_email_verified.assert_awaited_once_with(user.id)


def test_google_oidc_rejects_external_return_paths_and_replayed_state(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    client = TestClient(web_app.app)

    start = client.get(
        "/auth/google?next=https://attacker.example/collect", follow_redirects=False
    )
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    assert auth._safe_next("https://attacker.example/collect") == "/overview"
    assert auth._safe_next("//attacker.example/collect") == "/overview"

    rejected = client.get(
        "/auth/google/callback",
        params={"code": "code", "state": f"{state}-wrong"},
    )
    assert "Google sign-in could not be verified" in rejected.text

    replayed = client.get(
        "/auth/google/callback", params={"code": "code", "state": state}
    )
    assert "Google sign-in could not be verified" in replayed.text
