"""FastHTML application mounted alongside the retained FastVoice API."""
from __future__ import annotations

import os
import json
import secrets
from pathlib import Path

from fasthtml.common import *
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles

from api.constants import OSS_JWT_SECRET
from api.db import db_client
from api.routes.workflow import (
    CreateWorkflowRequest,
    UpdateWorkflowRequest,
    create_workflow as create_workflow_record,
    publish_workflow,
    update_workflow,
)
from api.routes.organization import save_model_configuration_v2
from api.schemas.ai_model_configuration import OrganizationAIModelConfigurationV2
from web import views
from web.auth import register_auth_routes
from web.components import app_shell
from web.landing import landing_page

ROOT = Path(__file__).resolve().parents[1]
SESSION_SECRET = os.getenv("FASTVOICE_SESSION_SECRET") or OSS_JWT_SECRET

app, rt = fast_app(
    live=False,
    pico=False,
    secret_key=SESSION_SECRET,
    hdrs=(
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Link(rel="icon", href="/static/favicon.svg", type="image/svg+xml"),
        Link(rel="stylesheet", href="/static/css/app.css"),
        Script(src="/static/js/app.js", defer=True),
    ),
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
register_auth_routes(rt)


async def _user(session):
    identity = session.get("user")
    if not isinstance(identity, dict) or not identity.get("id"):
        return None
    user = await db_client.get_user_by_id(int(identity["id"]))
    if user is None:
        session.clear()
    return user


async def _guard(session, active, title, builder):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        content = await builder(user) if callable(builder) else builder
    except Exception as exc:
        content = views.simple_view("FastVoice", title, f"This view could not be loaded: {exc}")
    if not isinstance(content, tuple):
        content = (content,)
    return app_shell(session, active, title, *content)


def _csrf_valid(session: dict, supplied: str) -> bool:
    expected = str(session.get("csrf_token", ""))
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))


@rt("/", methods=["GET"])
async def home(session):
    if await _user(session):
        return RedirectResponse("/overview", status_code=303)
    return landing_page()


@rt("/overview", methods=["GET"])
async def overview(session):
    return await _guard(session, "overview", "Overview", views.overview_view)


@rt("/workflow", methods=["GET"])
async def workflows(session, status: str = ""):
    return await _guard(session, "workflow", "Voice agents", lambda user: views.workflows_view(user, status or None))


@rt("/workflow/create", methods=["GET"])
async def workflow_create_get(session):
    async def content(_user):
        return (
            views.page_header("Build", "New voice agent", "Start with a focused agent name and opening instruction."),
            Section(
                Form(
                    views.csrf_input(session),
                    Label("Agent name", Input(name="name", required=True, autofocus=True, placeholder="Customer support concierge")),
                    Label("Opening instruction", Textarea(name="prompt", required=True, rows=7, placeholder="Greet the caller, explain who you are, and ask how you can help.")),
                    Div(A("Cancel", href="/workflow", cls="quiet-button"), Button("Create voice agent", type="submit", cls="primary-action"), cls="form-actions"),
                    method="post",
                    action="/workflow/create",
                    cls="stack-form",
                ),
                cls="panel form-panel",
            ),
        )
    return await _guard(session, "workflow", "New voice agent", content)


@rt("/workflow/create", methods=["POST"])
async def workflow_create_post(session, name: str = "", prompt: str = "", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse("/workflow/create", status_code=303)
    definition = {
        "nodes": [{
            "id": "1",
            "type": "startCall",
            "position": {"x": 160, "y": 180},
            "data": {"name": "Start Call", "prompt": prompt.strip()},
        }],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    workflow = await create_workflow_record(
        CreateWorkflowRequest(name=name.strip() or "Untitled voice agent", workflow_definition=definition),
        user=user,
    )
    session["flash"] = ("success", "Voice agent created. Add nodes and save a draft when ready.")
    return RedirectResponse(f"/workflow/{workflow.id}", status_code=303)


@rt("/workflow/{workflow_id}", methods=["GET"])
async def workflow_editor(session, workflow_id: int):
    return await _guard(
        session,
        "workflow",
        "Workflow editor",
        lambda user: views.workflow_editor_view(user, workflow_id, session),
    )


@rt("/workflow/{workflow_id}/save", methods=["POST"])
async def workflow_save(session, workflow_id: int, name: str = "", workflow_json: str = "", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse(f"/workflow/{workflow_id}", status_code=303)
    try:
        definition = json.loads(workflow_json)
        await update_workflow(
            workflow_id,
            UpdateWorkflowRequest(name=name.strip() or None, workflow_definition=definition),
            user=user,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        session["flash"] = ("error", f"Draft could not be saved: {exc}")
    else:
        session["flash"] = ("success", "Draft saved.")
    return RedirectResponse(f"/workflow/{workflow_id}", status_code=303)


@rt("/workflow/{workflow_id}/publish", methods=["POST"])
async def workflow_publish(session, workflow_id: int, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse(f"/workflow/{workflow_id}", status_code=303)
    await publish_workflow(workflow_id, user=user)
    session["flash"] = ("success", "Draft published.")
    return RedirectResponse(f"/workflow/{workflow_id}", status_code=303)


@rt("/campaigns", methods=["GET"])
async def campaigns(session):
    return await _guard(session, "campaigns", "Campaigns", views.campaigns_view)


@rt("/tools", methods=["GET"])
async def tools(session):
    return await _guard(session, "tools", "Tools", views.tools_view)


@rt("/files", methods=["GET"])
async def files(session):
    return await _guard(session, "files", "Knowledge", views.files_view)


@rt("/recordings", methods=["GET"])
async def recordings(session):
    return await _guard(session, "recordings", "Recordings", views.recordings_view)


@rt("/model-configurations", methods=["GET"])
async def models(session):
    return await _guard(session, "model-configurations", "Model configurations", lambda user: views.models_view(user, session))


@rt("/model-configurations/xai", methods=["POST"])
async def save_xai_configuration(
    session,
    api_key: str = "",
    realtime_model: str = "grok-voice-think-fast-1.0",
    voice: str = "ara",
    llm_model: str = "grok-4-fast-reasoning",
    csrf_token: str = "",
):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse("/model-configurations", status_code=303)
    key = api_key.strip() or os.getenv("XAI_API_KEY", "").strip()
    if not key:
        session["flash"] = ("error", "Enter an xAI API key or configure XAI_API_KEY on the server.")
        return RedirectResponse("/model-configurations", status_code=303)
    configuration = OrganizationAIModelConfigurationV2.model_validate({
        "mode": "byok",
        "byok": {
            "mode": "realtime",
            "realtime": {
                "realtime": {"provider": "grok_realtime", "api_key": key, "model": realtime_model.strip(), "voice": voice},
                "llm": {"provider": "openai", "api_key": key, "model": llm_model.strip(), "base_url": "https://api.x.ai/v1"},
            },
        },
    })
    try:
        await save_model_configuration_v2(configuration, user=user)
    except Exception as exc:
        detail = getattr(exc, "detail", None) or "xAI rejected the configuration."
        session["flash"] = ("error", str(detail))
    else:
        session["flash"] = ("success", "xAI realtime voice is connected and ready for agent tests.")
    return RedirectResponse("/model-configurations", status_code=303)


@rt("/telephony-configurations", methods=["GET"])
async def telephony(session):
    return await _guard(session, "telephony", "Telephony", views.telephony_view)


@rt("/reports", methods=["GET"])
async def reports(session):
    return await _guard(session, "reports", "Reports", lambda _user: _async_value(views.simple_view("Analyse", "Reports", "Explore call volume, duration, dispositions and workflow performance.")))


@rt("/api-keys", methods=["GET"])
async def api_keys(session):
    return await _guard(session, "api-keys", "API keys", lambda _user: _async_value(views.simple_view("Integrate", "API keys", "Create revocable API and service keys for automation and inference providers.")))


@rt("/settings", methods=["GET"])
async def settings(session):
    return await _guard(session, "settings", "Settings", lambda _user: _async_value(views.simple_view("Workspace", "Settings", "Manage organization preferences, tracing, telemetry and account access.")))


async def _async_value(value):
    return value


@rt("/developers", methods=["GET"])
def developers():
    return RedirectResponse("/api/v1/docs", status_code=307)


@rt("/healthz", methods=["GET"])
def healthz():
    return JSONResponse({"status": "ok", "service": "fastvoice"})


@rt("/robots.txt", methods=["GET"])
def robots():
    return Response("User-agent: *\nAllow: /\nSitemap: https://voice.fastsme.com/sitemap.xml\n", media_type="text/plain")


@rt("/sitemap.xml", methods=["GET"])
def sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://voice.fastsme.com/</loc></url><url><loc>https://voice.fastsme.com/developers</loc></url></urlset>"""
    return Response(xml, media_type="application/xml")
