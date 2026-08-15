"""Local, Google OIDC, and FastSME suite authentication for FastHTML."""
from __future__ import annotations

import asyncio
import os
import secrets
from urllib.parse import urlencode

import httpx
from fasthtml.common import *
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from starlette.responses import RedirectResponse

from api.constants import ENABLE_SIGNUP
from api.db import db_client
from api.services.organization_bootstrap import ensure_organization_bootstrapped
from api.utils.auth import create_jwt_token, hash_password, verify_password
from web.brand import APP_NAME
from web.components import WAVE_MARK, csrf_input, metadata
from web.suite_auth import enabled as suite_sso_enabled
from web.suite_auth import redeem_suite_ticket


def _client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "")


def _client_secret() -> str:
    return os.getenv("GOOGLE_CLIENT_SECRET", "")


def _redirect_uri(request) -> str:
    return os.getenv("GOOGLE_REDIRECT_URI") or str(request.url_for("google_callback"))


def _allowed(identity: dict) -> bool:
    email = str(identity.get("email", "")).lower()
    if not identity.get("email_verified") or not email:
        return False
    emails = {v.strip().lower() for v in os.getenv("GOOGLE_ALLOWED_EMAILS", "").split(",") if v.strip()}
    domains = {v.strip().lower() for v in os.getenv("GOOGLE_ALLOWED_DOMAINS", "").split(",") if v.strip()}
    if emails and email not in emails:
        return False
    return not domains or email.rsplit("@", 1)[-1] in domains


def _csrf_ok(session: dict, supplied: str) -> bool:
    expected = session.get("csrf_token", "")
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))


async def _establish(session: dict, user) -> None:
    if not user.selected_organization_id:
        org_provider_id = f"org_{user.provider_id}"
        organization, _ = await db_client.get_or_create_organization_by_provider_id(
            org_provider_id=org_provider_id,
            user_id=user.id,
        )
        await db_client.add_user_to_organization(user.id, organization.id)
        await db_client.update_user_selected_organization(user.id, organization.id)
        user.selected_organization_id = organization.id
    await ensure_organization_bootstrapped(
        user.selected_organization_id,
        created_by=str(user.provider_id),
    )
    session["user"] = {
        "id": user.id,
        "email": user.email or "",
        "organization_id": user.selected_organization_id,
        "provider_id": user.provider_id,
    }
    session["access_token"] = create_jwt_token(user.id, user.email or "")
    session["csrf_token"] = secrets.token_urlsafe(32)


def login_page(session: dict, error: str = "", email: str = ""):
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    google_enabled = bool(_client_id() and _client_secret())
    return (
        *metadata("Sign in", "Sign in to build and operate FastVoice agents.", "/login"),
        Div(
            A(Div(NotStr(WAVE_MARK), cls="brand-mark"), Span(APP_NAME), href="/", cls="public-brand auth-brand"),
            Div(
                Span("Welcome back", cls="eyebrow"),
                H1("Sign in to FastVoice"),
                P("Build, test and operate voice agents on infrastructure you control."),
                A("Continue with FastSME", href="/auth/fastoffice", cls="google-button") if suite_sso_enabled() else (
                    A("Continue with Google", href="/auth/google", cls="google-button") if google_enabled else Div("Suite sign-in is not configured for this environment.", cls="notice notice-info")
                ),
                Div(Span("or continue with email"), cls="auth-divider"),
                Form(
                    csrf_input(session),
                    Label("Email", Input(name="email", type="email", value=email, autocomplete="email", required=True)),
                    Label("Password", Input(name="password", type="password", autocomplete="current-password", required=True)),
                    P(error, cls="form-error", role="alert") if error else None,
                    Button("Sign in", type="submit", cls="primary-action wide"),
                    method="post",
                    action="/login",
                ),
                P("New to FastVoice? ", A("Create an account", href="/signup")) if ENABLE_SIGNUP else None,
                cls="auth-card",
            ),
            cls="auth-page",
        ),
    )


def signup_page(session: dict, error: str = "", email: str = "", name: str = ""):
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return (
        *metadata("Create account", "Create a FastVoice account.", "/signup"),
        Div(
            A(Div(NotStr(WAVE_MARK), cls="brand-mark"), Span(APP_NAME), href="/", cls="public-brand auth-brand"),
            Div(
                Span("Open voice automation", cls="eyebrow"), H1("Create your account"),
                Form(
                    csrf_input(session),
                    Label("Name", Input(name="name", value=name, autocomplete="name")),
                    Label("Email", Input(name="email", type="email", value=email, autocomplete="email", required=True)),
                    Label("Password", Input(name="password", type="password", minlength="8", autocomplete="new-password", required=True)),
                    P(error, cls="form-error", role="alert") if error else None,
                    Button("Create account", type="submit", cls="primary-action wide"),
                    method="post", action="/signup",
                ),
                P("Already registered? ", A("Sign in", href="/login")),
                cls="auth-card",
            ),
            cls="auth-page",
        ),
    )


def register_auth_routes(rt):
    @rt("/login", methods=["GET"])
    def login_get(session):
        if session.get("user"):
            return RedirectResponse("/overview", status_code=303)
        return login_page(session)

    @rt("/login", methods=["POST"])
    async def login_post(session, email: str = "", password: str = "", csrf_token: str = ""):
        if not _csrf_ok(session, csrf_token):
            return login_page(session, "Your session expired. Please try again.", email)
        user = await db_client.get_user_by_email(email.strip().lower())
        if not user or not user.password_hash or not verify_password(password, user.password_hash):
            return login_page(session, "Invalid email or password.", email)
        await _establish(session, user)
        return RedirectResponse("/overview", status_code=303)

    @rt("/signup", methods=["GET"])
    def signup_get(session):
        if not ENABLE_SIGNUP:
            return RedirectResponse("/login", status_code=303)
        return signup_page(session)

    @rt("/signup", methods=["POST"])
    async def signup_post(session, email: str = "", password: str = "", name: str = "", csrf_token: str = ""):
        if not ENABLE_SIGNUP:
            return RedirectResponse("/login", status_code=303)
        if not _csrf_ok(session, csrf_token):
            return signup_page(session, "Your session expired. Please try again.", email, name)
        if len(password) < 8 or "@" not in email:
            return signup_page(session, "Use a valid email and a password of at least 8 characters.", email, name)
        if await db_client.get_user_by_email(email):
            return signup_page(session, "An account with this email already exists.", email, name)
        user = await db_client.create_user_with_email(email, hash_password(password), name)
        await _establish(session, user)
        return RedirectResponse("/overview", status_code=303)

    @rt("/auth/google", methods=["GET"])
    def google_start(session, request):
        if not _client_id() or not _client_secret():
            return RedirectResponse("/login", status_code=303)
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session["google_oauth_state"] = state
        session["google_oauth_nonce"] = nonce
        query = urlencode({
            "client_id": _client_id(),
            "redirect_uri": _redirect_uri(request),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "prompt": "select_account",
        })
        return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}", status_code=303)

    @rt("/auth/google/callback", methods=["GET"], name="google_callback")
    async def google_callback(session, request, code: str = "", state: str = "", error: str = ""):
        expected_state = session.pop("google_oauth_state", "")
        expected_nonce = session.pop("google_oauth_nonce", "")
        if error or not code or not expected_state or not secrets.compare_digest(state, expected_state):
            return login_page(session, "Google sign-in could not be verified.")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "redirect_uri": _redirect_uri(request),
                "grant_type": "authorization_code",
            })
        if response.status_code != 200:
            return login_page(session, "Google sign-in could not be completed.")
        token = response.json().get("id_token", "")
        try:
            identity = await asyncio.to_thread(
                google_id_token.verify_oauth2_token,
                token,
                google_requests.Request(),
                _client_id(),
            )
        except Exception:  # noqa: BLE001 - Google token validation must fail closed.
            return login_page(session, "Google returned an invalid identity token.")
        if identity.get("nonce") != expected_nonce or not _allowed(identity):
            return login_page(session, "This Google account is not authorised for FastVoice.")
        email = identity["email"].lower()
        user = await db_client.get_user_by_email(email)
        if user is None:
            user, _ = await db_client.get_or_create_user_by_provider_id(f"google_{identity['sub']}")
            await db_client.update_user_email(user.id, email)
            user.email = email
        await _establish(session, user)
        return RedirectResponse("/overview", status_code=303)

    @rt("/auth/fastoffice", methods=["GET"])
    def fastoffice_start():
        if not suite_sso_enabled():
            return RedirectResponse("/login", status_code=303)
        issuer = os.getenv("FASTOFFICE_URL", "https://office.fastsme.com").rstrip("/")
        return RedirectResponse(f"{issuer}/launch/voice", status_code=303)

    @rt("/auth/suite/callback", methods=["GET"])
    async def suite_callback(session, ticket: str = ""):
        identity = await redeem_suite_ticket(ticket)
        if identity is None:
            return login_page(session, "Your FastSME session is invalid or expired.")
        email = str(identity["email"]).strip().lower()
        user = await db_client.get_user_by_email(email)
        if user is None:
            user, _ = await db_client.get_or_create_user_by_provider_id(f"fastoffice_{identity['sub']}")
            await db_client.update_user_email(user.id, email)
            user.email = email
        await _establish(session, user)
        session["suite_identity"] = {
            key: identity[key] for key in ("sub", "name", "org_id", "org_name", "role")
        }
        return RedirectResponse("/overview", status_code=303)

    @rt("/logout", methods=["POST"])
    def logout(session, csrf_token: str = ""):
        if _csrf_ok(session, csrf_token):
            session.clear()
        return RedirectResponse("/", status_code=303)
