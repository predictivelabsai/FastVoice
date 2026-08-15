"""Local, Google OIDC, and FastSME suite authentication for FastHTML."""

# ruff: noqa: F403, F405 - FastHTML's element DSL is intentionally exported.
from __future__ import annotations

import asyncio
import os
import re
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
from web.account_email import send_account_link
from web.auth_rate_limit import attempt_allowed
from web.components import WAVE_MARK, csrf_input, metadata
from web.suite_auth import enabled as suite_sso_enabled
from web.suite_auth import redeem_suite_ticket


def _client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "")


def _client_secret() -> str:
    return os.getenv("GOOGLE_CLIENT_SECRET", "")


def _redirect_uri(request) -> str:
    return os.getenv("GOOGLE_REDIRECT_URI") or str(request.url_for("google_callback"))


def _safe_next(value: str) -> str:
    return (
        value if value.startswith("/") and not value.startswith("//") else "/overview"
    )


def _route_with_next(path: str, next_path: str) -> str:
    return f"{path}?{urlencode({'next': _safe_next(next_path)})}"


def _allowed(identity: dict) -> bool:
    email = str(identity.get("email", "")).lower()
    if not identity.get("email_verified") or not email:
        return False
    emails = {
        v.strip().lower()
        for v in os.getenv("GOOGLE_ALLOWED_EMAILS", "").split(",")
        if v.strip()
    }
    domains = {
        v.strip().lower()
        for v in os.getenv("GOOGLE_ALLOWED_DOMAINS", "").split(",")
        if v.strip()
    }
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


def login_page(
    session: dict,
    error: str = "",
    email: str = "",
    message: str = "",
    next_path: str = "/overview",
):
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    google_enabled = bool(_client_id() and _client_secret())
    return (
        *metadata(
            "Sign in", "Sign in to build and operate FastVoice agents.", "/login"
        ),
        Div(
            A(
                Div(NotStr(WAVE_MARK), cls="brand-mark"),
                Span(APP_NAME),
                href="/",
                cls="public-brand auth-brand",
            ),
            Div(
                Span("Welcome back", cls="eyebrow"),
                H1("Sign in to FastVoice"),
                P(
                    "Build, test and operate voice agents on infrastructure you control."
                ),
                A(
                    "Continue with Google",
                    href=_route_with_next("/auth/google", next_path),
                    cls="google-button",
                )
                if google_enabled
                else Div(
                    "Google sign-in is not configured for this environment.",
                    cls="notice notice-info",
                ),
                A(
                    "Continue with FastSME",
                    href=_route_with_next("/auth/fastoffice", next_path),
                    cls="google-button",
                )
                if suite_sso_enabled()
                else None,
                Div(Span("or continue with email"), cls="auth-divider"),
                Form(
                    csrf_input(session),
                    Label(
                        "Email",
                        Input(
                            name="email",
                            type="email",
                            value=email,
                            autocomplete="email",
                            required=True,
                        ),
                    ),
                    Label(
                        "Password",
                        Input(
                            name="password",
                            type="password",
                            autocomplete="current-password",
                            required=True,
                        ),
                    ),
                    Input(type="hidden", name="next_path", value=_safe_next(next_path)),
                    P(error, cls="form-error", role="alert") if error else None,
                    P(message, cls="notice notice-success", role="status")
                    if message
                    else None,
                    Button("Sign in", type="submit", cls="primary-action wide"),
                    method="post",
                    action="/login",
                ),
                A("Forgot password?", href="/forgot-password", cls="text-action"),
                P("New to FastVoice? ", A("Create an account", href="/signup"))
                if ENABLE_SIGNUP
                else None,
                cls="auth-card",
            ),
            cls="auth-page",
        ),
    )


def signup_page(
    session: dict,
    error: str = "",
    email: str = "",
    name: str = "",
    message: str = "",
):
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return (
        *metadata("Create account", "Create a FastVoice account.", "/signup"),
        Div(
            A(
                Div(NotStr(WAVE_MARK), cls="brand-mark"),
                Span(APP_NAME),
                href="/",
                cls="public-brand auth-brand",
            ),
            Div(
                Span("Open voice automation", cls="eyebrow"),
                H1("Create your account"),
                A("Continue with Google", href="/auth/google", cls="google-button")
                if _client_id() and _client_secret()
                else None,
                Div(Span("or register with email"), cls="auth-divider"),
                Form(
                    csrf_input(session),
                    Label("Name", Input(name="name", value=name, autocomplete="name")),
                    Label(
                        "Email",
                        Input(
                            name="email",
                            type="email",
                            value=email,
                            autocomplete="email",
                            required=True,
                        ),
                    ),
                    Label(
                        "Password",
                        Input(
                            name="password",
                            type="password",
                            minlength="10",
                            autocomplete="new-password",
                            required=True,
                        ),
                    ),
                    Label(
                        "Confirm password",
                        Input(
                            name="password_confirm",
                            type="password",
                            minlength="10",
                            autocomplete="new-password",
                            required=True,
                        ),
                    ),
                    P(error, cls="form-error", role="alert") if error else None,
                    P(message, cls="notice notice-success", role="status")
                    if message
                    else None,
                    Button("Create account", type="submit", cls="primary-action wide"),
                    method="post",
                    action="/signup",
                ),
                P(
                    "We will email you a verification link before this account can sign in.",
                    cls="form-help",
                ),
                P("Already registered? ", A("Sign in", href="/login")),
                cls="auth-card",
            ),
            cls="auth-page",
        ),
    )


def forgot_password_page(session: dict, message: str = "", error: str = ""):
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return (
        *metadata(
            "Reset password", "Reset your FastVoice password.", "/forgot-password"
        ),
        Div(
            A(
                Div(NotStr(WAVE_MARK), cls="brand-mark"),
                Span(APP_NAME),
                href="/",
                cls="public-brand auth-brand",
            ),
            Div(
                Span("Account recovery", cls="eyebrow"),
                H1("Reset your password"),
                P("Enter your email and we will send a single-use reset link."),
                Form(
                    csrf_input(session),
                    Label(
                        "Email",
                        Input(
                            name="email",
                            type="email",
                            autocomplete="email",
                            required=True,
                        ),
                    ),
                    P(error, cls="form-error", role="alert") if error else None,
                    P(message, cls="notice notice-success", role="status")
                    if message
                    else None,
                    Button("Send reset link", type="submit", cls="primary-action wide"),
                    method="post",
                    action="/forgot-password",
                ),
                P(A("Back to sign in", href="/login")),
                cls="auth-card",
            ),
            cls="auth-page",
        ),
    )


def reset_password_page(session: dict, token: str, error: str = ""):
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return (
        *metadata("Choose password", "Choose a new FastVoice password.", "/auth/reset"),
        Div(
            A(
                Div(NotStr(WAVE_MARK), cls="brand-mark"),
                Span(APP_NAME),
                href="/",
                cls="public-brand auth-brand",
            ),
            Div(
                Span("Account recovery", cls="eyebrow"),
                H1("Choose a new password"),
                Form(
                    csrf_input(session),
                    Input(type="hidden", name="token", value=token),
                    Label(
                        "New password",
                        Input(
                            name="password",
                            type="password",
                            minlength="10",
                            autocomplete="new-password",
                            required=True,
                        ),
                    ),
                    Label(
                        "Confirm password",
                        Input(
                            name="password_confirm",
                            type="password",
                            minlength="10",
                            autocomplete="new-password",
                            required=True,
                        ),
                    ),
                    P(error, cls="form-error", role="alert") if error else None,
                    Button("Update password", type="submit", cls="primary-action wide"),
                    method="post",
                    action="/auth/reset",
                ),
                cls="auth-card",
            ),
            cls="auth-page",
        ),
    )


def register_auth_routes(rt):
    @rt("/login", methods=["GET"])
    def login_get(session, next: str = "/overview", message: str = ""):
        if session.get("user"):
            return RedirectResponse("/overview", status_code=303)
        return login_page(session, message=message, next_path=_safe_next(next))

    @rt("/login", methods=["POST"])
    async def login_post(
        session,
        email: str = "",
        password: str = "",
        next_path: str = "/overview",
        csrf_token: str = "",
    ):
        if not _csrf_ok(session, csrf_token):
            return login_page(
                session,
                "Your session expired. Please try again.",
                email,
                next_path=next_path,
            )
        normalized = email.strip().lower()
        if not await attempt_allowed(normalized, "login", limit=10, window_seconds=900):
            return login_page(
                session,
                "Too many attempts. Please try again later.",
                email,
                next_path=next_path,
            )
        user = await db_client.get_user_by_email(normalized)
        if (
            not user
            or not user.password_hash
            or not user.email_verified
            or not verify_password(password, user.password_hash)
        ):
            return login_page(
                session, "Invalid email or password.", email, next_path=next_path
            )
        await _establish(session, user)
        return RedirectResponse(_safe_next(next_path), status_code=303)

    @rt("/signup", methods=["GET"])
    def signup_get(session):
        if not ENABLE_SIGNUP:
            return RedirectResponse("/login", status_code=303)
        return signup_page(session)

    @rt("/signup", methods=["POST"])
    async def signup_post(
        session,
        email: str = "",
        password: str = "",
        password_confirm: str = "",
        name: str = "",
        csrf_token: str = "",
    ):
        if not ENABLE_SIGNUP:
            return RedirectResponse("/login", status_code=303)
        if not _csrf_ok(session, csrf_token):
            return signup_page(
                session, "Your session expired. Please try again.", email, name
            )
        normalized = email.strip().lower()
        if (
            not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized)
            or len(password) < 10
        ):
            return signup_page(
                session,
                "Use a valid email and a password of at least 10 characters.",
                email,
                name,
            )
        if password != password_confirm:
            return signup_page(session, "Passwords do not match.", email, name)
        if not await attempt_allowed(
            normalized, "signup", limit=5, window_seconds=3600
        ):
            return signup_page(
                session, "Too many attempts. Please try again later.", email, name
            )
        user = await db_client.get_user_by_email(normalized)
        if user is not None and user.email_verified:
            return signup_page(
                session,
                message="If this address can be registered, a verification email is on its way.",
            )
        if user is None:
            user = await db_client.create_user_with_email(
                normalized, hash_password(password), name
            )
        else:
            await db_client.update_user_password(user.id, hash_password(password))
        token = await db_client.issue_user_auth_token(user.id, "verify", 24 * 3600)
        if not await send_account_link(normalized, "verify", token):
            return signup_page(
                session,
                "Verification email could not be sent. Please try again shortly.",
                email,
                name,
            )
        return login_page(session, message="Check your email to verify your account.")

    @rt("/auth/verify/{token}", methods=["GET"])
    async def verify_email(session, token: str):
        user = await db_client.consume_user_auth_token(token, "verify")
        if user is None:
            return login_page(session, "The verification link is invalid or expired.")
        await db_client.mark_user_email_verified(user.id)
        user.email_verified = True
        await _establish(session, user)
        return RedirectResponse("/overview", status_code=303)

    @rt("/forgot-password", methods=["GET"])
    def forgot_password_get(session):
        return forgot_password_page(session)

    @rt("/forgot-password", methods=["POST"])
    async def forgot_password_post(session, email: str = "", csrf_token: str = ""):
        if not _csrf_ok(session, csrf_token):
            return forgot_password_page(
                session, error="Your session expired. Please try again."
            )
        normalized = email.strip().lower()
        if await attempt_allowed(normalized, "forgot", limit=5, window_seconds=3600):
            user = await db_client.get_user_by_email(normalized)
            if user is not None and user.email_verified:
                token = await db_client.issue_user_auth_token(user.id, "reset", 3600)
                await send_account_link(normalized, "reset", token)
        return forgot_password_page(
            session, message="If an account exists, a reset link is on its way."
        )

    @rt("/auth/reset/{token}", methods=["GET"])
    def reset_password_get(session, token: str):
        return reset_password_page(session, token)

    @rt("/auth/reset", methods=["POST"])
    async def reset_password_post(
        session,
        token: str = "",
        password: str = "",
        password_confirm: str = "",
        csrf_token: str = "",
    ):
        if not _csrf_ok(session, csrf_token):
            return reset_password_page(
                session, token, "Your session expired. Please try again."
            )
        if len(password) < 10 or password != password_confirm:
            return reset_password_page(
                session,
                token,
                "Passwords must match and contain at least 10 characters.",
            )
        user = await db_client.consume_user_auth_token(token, "reset")
        if user is None:
            return reset_password_page(
                session, token, "The reset link is invalid or expired."
            )
        await db_client.update_user_password(user.id, hash_password(password))
        return login_page(
            session, message="Your password has been updated. You can sign in now."
        )

    @rt("/auth/google", methods=["GET"])
    def google_start(session, request, next: str = "/overview"):
        if not _client_id() or not _client_secret():
            return RedirectResponse("/login", status_code=303)
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session["google_oauth_state"] = state
        session["google_oauth_nonce"] = nonce
        session["auth_next"] = _safe_next(next)
        query = urlencode(
            {
                "client_id": _client_id(),
                "redirect_uri": _redirect_uri(request),
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "prompt": "select_account",
            }
        )
        return RedirectResponse(
            f"https://accounts.google.com/o/oauth2/v2/auth?{query}", status_code=303
        )

    @rt("/auth/google/callback", methods=["GET"], name="google_callback")
    async def google_callback(
        session, request, code: str = "", state: str = "", error: str = ""
    ):
        expected_state = session.pop("google_oauth_state", "")
        expected_nonce = session.pop("google_oauth_nonce", "")
        if (
            error
            or not code
            or not expected_state
            or not secrets.compare_digest(state, expected_state)
        ):
            return login_page(session, "Google sign-in could not be verified.")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": _client_id(),
                    "client_secret": _client_secret(),
                    "redirect_uri": _redirect_uri(request),
                    "grant_type": "authorization_code",
                },
            )
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
            return login_page(
                session, "This Google account is not authorised for FastVoice."
            )
        email = identity["email"].lower()
        user = await db_client.get_user_by_email(email)
        if user is None:
            user, _ = await db_client.get_or_create_user_by_provider_id(
                f"google_{identity['sub']}"
            )
            await db_client.update_user_email(user.id, email)
            user.email = email
        await db_client.mark_user_email_verified(user.id)
        user.email_verified = True
        await _establish(session, user)
        return RedirectResponse(
            _safe_next(session.pop("auth_next", "/overview")), status_code=303
        )

    @rt("/auth/fastoffice", methods=["GET"])
    def fastoffice_start(session, next: str = "/overview"):
        if not suite_sso_enabled():
            return RedirectResponse("/login", status_code=303)
        issuer = os.getenv("FASTOFFICE_URL", "https://office.fastsme.com").rstrip("/")
        session["auth_next"] = _safe_next(next)
        return RedirectResponse(f"{issuer}/launch/voice", status_code=303)

    @rt("/auth/suite/callback", methods=["GET"])
    async def suite_callback(session, ticket: str = ""):
        identity = await redeem_suite_ticket(ticket)
        if identity is None:
            return login_page(session, "Your FastSME session is invalid or expired.")
        email = str(identity["email"]).strip().lower()
        user = await db_client.get_user_by_email(email)
        if user is None:
            user, _ = await db_client.get_or_create_user_by_provider_id(
                f"fastoffice_{identity['sub']}"
            )
            await db_client.update_user_email(user.id, email)
            user.email = email
        await db_client.mark_user_email_verified(user.id)
        user.email_verified = True
        await _establish(session, user)
        session["suite_identity"] = {
            key: identity[key] for key in ("sub", "name", "org_id", "org_name", "role")
        }
        return RedirectResponse(
            _safe_next(session.pop("auth_next", "/overview")), status_code=303
        )

    @rt("/logout", methods=["POST"])
    def logout(session, csrf_token: str = ""):
        if _csrf_ok(session, csrf_token):
            session.clear()
        return RedirectResponse("/", status_code=303)
