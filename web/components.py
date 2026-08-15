"""Shared FastHTML components for the public site and application shell."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable

from fasthtml.common import *

from web.brand import APP_NAME, CANONICAL_URL, DESCRIPTION


WAVE_MARK = """<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M3 17h4l2-8 4 16 4-20 4 24 3-12h5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>"""

NAV_ITEMS = (
    ("overview", "/overview", "Overview"),
    ("workflow", "/workflow", "Voice agents"),
    ("campaigns", "/campaigns", "Campaigns"),
    ("reports", "/reports", "Reports"),
    ("model-configurations", "/model-configurations", "Models"),
    ("tools", "/tools", "Tools"),
    ("files", "/files", "Knowledge"),
    ("recordings", "/recordings", "Recordings"),
    ("telephony", "/telephony-configurations", "Telephony"),
    ("api-keys", "/api-keys", "API keys"),
    ("settings", "/settings", "Settings"),
)


def metadata(title: str, description: str = DESCRIPTION, path: str = "/"):
    page_title = APP_NAME if title == APP_NAME else f"{title} · {APP_NAME}"
    canonical = f"{CANONICAL_URL}{path if path.startswith('/') else '/' + path}"
    return (
        Title(page_title),
        Meta(name="description", content=description),
        Link(rel="canonical", href=canonical),
        Meta(property="og:title", content=page_title),
        Meta(property="og:description", content=description),
        Meta(property="og:url", content=canonical),
        Meta(property="og:type", content="website"),
        Meta(name="twitter:card", content="summary_large_image"),
    )


def csrf_input(session: dict[str, Any]):
    return Input(type="hidden", name="csrf_token", value=session.get("csrf_token", ""))


def flash(session: dict[str, Any]):
    message = session.pop("flash", None)
    if not message:
        return None
    kind, text = message if isinstance(message, (tuple, list)) else ("info", message)
    return Div(text, cls=f"notice notice-{kind}", role="status")


def empty_state(title: str, body: str, action: Any | None = None):
    return Div(
        Div(NotStr(WAVE_MARK), cls="empty-mark"),
        H2(title),
        P(body),
        action,
        cls="empty-state",
    )


def status_badge(value: Any):
    text = str(getattr(value, "value", value) or "unknown")
    slug = "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")
    return Span(text.replace("_", " ").title(), cls=f"badge badge-{slug}")


def format_time(value: Any):
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone().strftime("%d %b %Y, %H:%M")
    return str(value)


def data_table(headers: Iterable[str], rows: Iterable[Iterable[Any]], *, cls: str = ""):
    rows = list(rows)
    return Div(
        Table(
            Thead(Tr(*[Th(header) for header in headers])),
            Tbody(*[Tr(*[Td(cell) for cell in row]) for row in rows]),
        ),
        cls=f"table-wrap {cls}".strip(),
    )


def metric(label: str, value: Any, helper: str = ""):
    return Article(
        P(label, cls="metric-label"),
        Strong(str(value), cls="metric-value"),
        P(helper, cls="metric-help") if helper else None,
        cls="metric",
    )


def page_header(eyebrow: str, title: str, subtitle: str = "", actions: Any | None = None):
    return Header(
        Div(Span(eyebrow, cls="eyebrow"), H1(title), P(subtitle) if subtitle else None),
        Div(actions, cls="page-actions") if actions else None,
        cls="page-header",
    )


def app_shell(
    session: dict[str, Any],
    active: str,
    title: str,
    *content: Any,
    description: str = DESCRIPTION,
):
    user = session.get("user") or {}
    email = user.get("email", "") if isinstance(user, dict) else str(user)
    display = email.split("@", 1)[0] if email else "Account"
    nav = Nav(
        A(Div(NotStr(WAVE_MARK), cls="brand-mark"), Span(APP_NAME), href="/overview", cls="app-brand"),
        Div(
            *[
                A(label, href=href, cls="nav-link active" if key == active else "nav-link")
                for key, href, label in NAV_ITEMS
            ],
            cls="nav-links",
        ),
        Div(
            Div(Span(display[:1].upper(), cls="avatar"), Div(Strong(display), Small(email)), cls="account-line"),
            Form(csrf_input(session), Button("Sign out", type="submit", cls="quiet-button"), method="post", action="/logout"),
            cls="nav-account",
        ),
        cls="sidebar",
        aria_label="Primary",
    )
    mobile = Header(
        A(Div(NotStr(WAVE_MARK), cls="brand-mark"), Span(APP_NAME), href="/overview", cls="app-brand"),
        Button("Menu", type="button", cls="mobile-menu-button", data_menu_toggle="true", aria_label="Open navigation"),
        cls="mobile-header",
    )
    return (
        *metadata(title, description, "/" if active == "overview" else f"/{active}"),
        Div(
            nav,
            mobile,
            Main(flash(session), *content, cls="app-main"),
            cls="app-frame",
        ),
    )
