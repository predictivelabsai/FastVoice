"""FastHTML application mounted alongside the retained FastVoice API."""
# ruff: noqa: F403, F405 - FastHTML's element DSL is intentionally exported.
from __future__ import annotations

import os
import json
import mimetypes
import re
import secrets
import tempfile
import uuid
from pathlib import Path

from fastapi import UploadFile
from fasthtml.common import *
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles

from api.constants import OSS_JWT_SECRET
from api.db import db_client
from api.routes.workflow import (
    CreateWorkflowRequest,
    UpdateWorkflowRequest,
    UpdateWorkflowStatusRequest,
    create_workflow as create_workflow_record,
    duplicate_workflow_endpoint,
    get_workflow as get_workflow_record,
    publish_workflow,
    update_workflow,
    update_workflow_status,
)
from api.routes.campaign import (
    CreateCampaignRequest,
    RetryConfigRequest,
    create_campaign as create_campaign_record,
    pause_campaign,
    resume_campaign,
    start_campaign,
)
from api.routes.tool import (
    create_tool as create_tool_record,
    delete_tool as archive_tool_record,
    refresh_mcp_tools,
    test_tool as test_tool_record,
    unarchive_tool as unarchive_tool_record,
    update_tool as update_tool_record,
)
from api.schemas.tool import CreateToolRequest, ToolTestRequest, UpdateToolRequest
from api.routes.organization import save_model_configuration_v2
from api.routes.organization import save_preferences
from api.routes.organization import (
    create_telephony_configuration,
    delete_telephony_configuration,
    update_telephony_configuration,
)
from api.routes.user import (
    CreateAPIKeyRequest,
    archive_api_key as archive_api_key_record,
    create_api_key as create_api_key_record,
    reactivate_api_key as reactivate_api_key_record,
)
from api.schemas.ai_model_configuration import OrganizationAIModelConfigurationV2
from api.schemas.organization_preferences import OrganizationPreferences
from api.schemas.telephony_config import TelephonyConfigurationCreateRequest, TelephonyConfigurationUpdateRequest
from api.routes.knowledge_base import delete_document, process_document
from api.schemas.knowledge_base import ProcessDocumentRequestSchema
from api.routes.workflow_recording import (
    _generate_unique_recording_id,
    create_recordings,
    delete_recording,
)
from api.schemas.workflow_recording import (
    BatchRecordingCreateRequestSchema,
    RecordingCreateRequestSchema,
)
from api.services.storage import storage_fs
from api.routes.workflow_embed import (
    EmbedTokenRequest,
    create_or_update_embed_token,
    deactivate_embed_token,
    get_embed_token,
)
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


@rt("/workflow/{workflow_id}/status", methods=["POST"])
async def workflow_status(session, workflow_id: int, status: str = "archived", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if _csrf_valid(session, csrf_token):
        await update_workflow_status(workflow_id, UpdateWorkflowStatusRequest(status=status), user=user)
        session["flash"] = ("success", f"Voice agent marked {status}.")
    else:
        session["flash"] = ("error", "Your session expired. Please try again.")
    return RedirectResponse(f"/workflow/{workflow_id}", status_code=303)


@rt("/workflow/{workflow_id}/duplicate", methods=["POST"])
async def workflow_duplicate(session, workflow_id: int, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse(f"/workflow/{workflow_id}", status_code=303)
    duplicated = await duplicate_workflow_endpoint(workflow_id, user=user)
    session["flash"] = ("success", "Voice agent duplicated.")
    return RedirectResponse(f"/workflow/{duplicated['id']}", status_code=303)


@rt("/workflow/{workflow_id}/embed-token", methods=["POST"])
async def workflow_embed_create(request, session, workflow_id: int, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
    else:
        await create_or_update_embed_token(workflow_id, request=request, embed_request=EmbedTokenRequest(expires_in_days=None), user=user)
        session["flash"] = ("success", "Web widget token created.")
    return RedirectResponse(f"/workflow/{workflow_id}", status_code=303)


@rt("/workflow/{workflow_id}/embed-token/deactivate", methods=["POST"])
async def workflow_embed_deactivate(session, workflow_id: int, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if _csrf_valid(session, csrf_token):
        await deactivate_embed_token(workflow_id, user=user)
        session["flash"] = ("success", "Web widget token deactivated.")
    else:
        session["flash"] = ("error", "Your session expired. Please try again.")
    return RedirectResponse(f"/workflow/{workflow_id}", status_code=303)


@rt("/workflow/{workflow_id}/preview", methods=["GET"])
async def workflow_preview(session, workflow_id: int):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    token = await get_embed_token(workflow_id, request=None, user=user)
    if token is None:
        session["flash"] = ("error", "Create a web widget token first.")
        return RedirectResponse(f"/workflow/{workflow_id}", status_code=303)
    workflow = await get_workflow_record(workflow_id, user=user)
    script_src = f"/static/js/embed.js?token={token.token}&environment=production&apiEndpoint={os.getenv('PUBLIC_BASE_URL', 'https://voice.fastsme.com')}"
    return (
        Title(f"Preview · {workflow.name} · FastVoice"),
        Link(rel="stylesheet", href="/static/css/app.css"),
        Main(
            A("← Back to editor", href=f"/workflow/{workflow_id}", cls="back-link"),
            Div(Span("Browser test", cls="eyebrow"), H1(workflow.name), P("Use the FastVoice control in the corner to start a microphone call or text conversation."), cls="preview-card"),
            cls="preview-page",
        ),
        Script(src=script_src, data_fastvoice_context=json.dumps({"preview": True, "workflow_id": workflow_id})),
    )


@rt("/campaigns", methods=["GET"])
async def campaigns(session):
    return await _guard(session, "campaigns", "Campaigns", views.campaigns_view)


@rt("/campaigns/new", methods=["GET"])
async def campaign_new_get(session):
    return await _guard(session, "campaigns", "New campaign", lambda user: views.campaign_new_view(user, session))


@rt("/campaigns/new", methods=["POST"])
async def campaign_new_post(
    session,
    source_file: UploadFile,
    name: str = "",
    workflow_id: int = 0,
    telephony_configuration_id: int = 0,
    max_concurrency: int = 1,
    max_retries: int = 2,
    retry_delay_seconds: int = 120,
    csrf_token: str = "",
):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse("/campaigns/new", status_code=303)
    filename = Path(source_file.filename or "contacts.csv").name
    if not filename.lower().endswith(".csv"):
        session["flash"] = ("error", "Campaign sources must be CSV files.")
        return RedirectResponse("/campaigns/new", status_code=303)
    payload = await source_file.read(10_485_761)
    if not payload or len(payload) > 10_485_760:
        session["flash"] = ("error", "The CSV must be between 1 byte and 10 MB.")
        return RedirectResponse("/campaigns/new", status_code=303)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename)
    source_id = f"campaigns/{user.selected_organization_id}/{uuid.uuid4().hex}_{safe_name}"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temporary:
            temporary.write(payload)
            temporary_path = temporary.name
        if not await storage_fs.aupload_file(temporary_path, source_id):
            raise RuntimeError("Storage rejected the campaign CSV")
        campaign = await create_campaign_record(
            CreateCampaignRequest(
                name=name.strip() or "Outbound campaign",
                workflow_id=workflow_id,
                source_type="csv",
                source_id=source_id,
                telephony_configuration_id=telephony_configuration_id or None,
                max_concurrency=max_concurrency,
                retry_config=RetryConfigRequest(max_retries=max_retries, retry_delay_seconds=retry_delay_seconds),
            ),
            user=user,
        )
    except Exception as exc:
        session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
        return RedirectResponse("/campaigns/new", status_code=303)
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
    session["flash"] = ("success", "Campaign created and CSV validated.")
    return RedirectResponse(f"/campaigns/{campaign.id}", status_code=303)


@rt("/campaigns/{campaign_id}", methods=["GET"])
async def campaign_detail(session, campaign_id: int):
    return await _guard(session, "campaigns", "Campaign", lambda user: views.campaign_detail_view(user, campaign_id, session))


@rt("/campaigns/{campaign_id}/{action}", methods=["POST"])
async def campaign_action(session, campaign_id: int, action: str, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse(f"/campaigns/{campaign_id}", status_code=303)
    handlers = {"start": start_campaign, "pause": pause_campaign, "resume": resume_campaign}
    handler = handlers.get(action)
    if handler is None:
        return Response("Unknown campaign action", status_code=404)
    try:
        await handler(campaign_id, user=user)
    except Exception as exc:
        session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
    else:
        session["flash"] = ("success", f"Campaign {action} requested.")
    return RedirectResponse(f"/campaigns/{campaign_id}", status_code=303)


@rt("/tools", methods=["GET"])
async def tools(session):
    return await _guard(session, "tools", "Tools", views.tools_view)


@rt("/tools/new", methods=["GET"])
async def tool_new_get(session):
    return await _guard(session, "tools", "New tool", lambda user: views.tool_form_view(user, session))


@rt("/tools/new", methods=["POST"])
async def tool_new_post(session, name: str = "", description: str = "", category: str = "http_api", definition_json: str = "", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse("/tools/new", status_code=303)
    try:
        request = CreateToolRequest.model_validate({"name": name.strip(), "description": description.strip() or None, "category": category, "definition": json.loads(definition_json)})
        tool = await create_tool_record(request, user=user)
    except Exception as exc:
        session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
        return RedirectResponse("/tools/new", status_code=303)
    session["flash"] = ("success", "Tool created.")
    return RedirectResponse(f"/tools/{tool.tool_uuid}", status_code=303)


@rt("/tools/{tool_uuid}", methods=["GET"])
async def tool_detail(session, tool_uuid: str):
    return await _guard(session, "tools", "Tool", lambda user: views.tool_form_view(user, session, tool_uuid))


@rt("/tools/{tool_uuid}", methods=["POST"])
async def tool_update(session, tool_uuid: str, name: str = "", description: str = "", category: str = "http_api", definition_json: str = "", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse(f"/tools/{tool_uuid}", status_code=303)
    try:
        definition = CreateToolRequest.model_validate({"name": name.strip(), "description": description.strip() or None, "category": category, "definition": json.loads(definition_json)}).definition
        await update_tool_record(tool_uuid, UpdateToolRequest(name=name.strip(), description=description.strip() or None, definition=definition), user=user)
    except Exception as exc:
        session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
    else:
        session["flash"] = ("success", "Tool saved.")
    return RedirectResponse(f"/tools/{tool_uuid}", status_code=303)


@rt("/tools/{tool_uuid}/{action}", methods=["POST"])
async def tool_action(session, tool_uuid: str, action: str, llm_params_json: str = "{}", preset_params_json: str = "{}", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse(f"/tools/{tool_uuid}", status_code=303)
    try:
        if action == "archive":
            await archive_tool_record(tool_uuid, user=user)
        elif action == "unarchive":
            await unarchive_tool_record(tool_uuid, user=user)
        elif action == "refresh":
            await refresh_mcp_tools(tool_uuid, user=user)
        elif action == "test":
            result = await test_tool_record(tool_uuid, ToolTestRequest(llm_params=json.loads(llm_params_json), preset_params=json.loads(preset_params_json)), user=user)
            content = await views.tool_form_view(user, session, tool_uuid, test_result=result)
            return app_shell(session, "tools", "Tool", *content)
        else:
            return Response("Unknown tool action", status_code=404)
    except Exception as exc:
        session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
    else:
        session["flash"] = ("success", f"Tool {action} completed.")
    return RedirectResponse(f"/tools/{tool_uuid}", status_code=303)


@rt("/files", methods=["GET"])
async def files(session):
    return await _guard(session, "files", "Knowledge", lambda user: views.files_view(user, session))


@rt("/files/upload", methods=["POST"])
async def file_upload(session, document_file: UploadFile, retrieval_mode: str = "chunked", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse("/files", status_code=303)
    filename = Path(document_file.filename or "document").name
    payload = await document_file.read(100_000_001)
    if not payload or len(payload) > 100_000_000:
        session["flash"] = ("error", "Documents must be between 1 byte and 100 MB.")
        return RedirectResponse("/files", status_code=303)
    document_uuid = str(uuid.uuid4())
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename)
    storage_key = f"knowledge_base/{user.selected_organization_id}/{document_uuid}/{safe_name}"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(safe_name).suffix, delete=False) as temporary:
            temporary.write(payload)
            temporary_path = temporary.name
        if not await storage_fs.aupload_file(temporary_path, storage_key):
            raise RuntimeError("Storage rejected the document")
        await process_document(ProcessDocumentRequestSchema(document_uuid=document_uuid, s3_key=storage_key, retrieval_mode=retrieval_mode), user=user)
    except Exception as exc:
        session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
    else:
        session["flash"] = ("success", "Document uploaded. Processing has been queued.")
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
    return RedirectResponse("/files", status_code=303)


@rt("/files/{document_uuid}/delete", methods=["POST"])
async def file_delete(session, document_uuid: str, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if _csrf_valid(session, csrf_token):
        await delete_document(document_uuid, user=user)
        session["flash"] = ("success", "Document deleted.")
    else:
        session["flash"] = ("error", "Your session expired. Please try again.")
    return RedirectResponse("/files", status_code=303)


@rt("/recordings", methods=["GET"])
async def recordings(session):
    return await _guard(session, "recordings", "Recordings", lambda user: views.recordings_view(user, session))


@rt("/recordings/upload", methods=["POST"])
async def recording_upload(session, audio_file: UploadFile, transcript: str = "", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse("/recordings", status_code=303)
    filename = Path(audio_file.filename or "recording.wav").name
    payload = await audio_file.read(5_242_881)
    if not payload or len(payload) > 5_242_880:
        session["flash"] = ("error", "Recordings must be between 1 byte and 5 MB.")
        return RedirectResponse("/recordings", status_code=303)
    recording_id = await _generate_unique_recording_id(user.selected_organization_id)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", filename)
    storage_key = f"recordings/{user.selected_organization_id}/{recording_id}/{safe_name}"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(safe_name).suffix, delete=False) as temporary:
            temporary.write(payload)
            temporary_path = temporary.name
        if not await storage_fs.aupload_file(temporary_path, storage_key):
            raise RuntimeError("Storage rejected the recording")
        await create_recordings(BatchRecordingCreateRequestSchema(recordings=[RecordingCreateRequestSchema(recording_id=recording_id, transcript=transcript.strip(), storage_key=storage_key, metadata={"filename": safe_name, "file_size": len(payload), "mime_type": audio_file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"})]), user=user)
    except Exception as exc:
        session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
    else:
        session["flash"] = ("success", "Recording uploaded.")
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
    return RedirectResponse("/recordings", status_code=303)


@rt("/recordings/{recording_id}/delete", methods=["POST"])
async def recording_delete(session, recording_id: str, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if _csrf_valid(session, csrf_token):
        await delete_recording(recording_id, user=user)
        session["flash"] = ("success", "Recording deleted.")
    else:
        session["flash"] = ("error", "Your session expired. Please try again.")
    return RedirectResponse("/recordings", status_code=303)


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


@rt("/telephony-configurations/new", methods=["GET"])
async def telephony_new_get(session, provider: str = ""):
    return await _guard(session, "telephony", "New telephony configuration", lambda user: views.telephony_form_view(user, session, provider=provider or None))


@rt("/telephony-configurations/new", methods=["POST"])
async def telephony_new_post(session, name: str = "", provider: str = "", config_json: str = "", is_default_outbound: str = "", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse("/telephony-configurations/new", status_code=303)
    try:
        config = json.loads(config_json)
        config["provider"] = provider or config.get("provider")
        request = TelephonyConfigurationCreateRequest.model_validate({"name": name.strip(), "is_default_outbound": is_default_outbound == "true", "config": config})
        created = await create_telephony_configuration(request, user=user)
    except Exception as exc:
        session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
        return RedirectResponse(f"/telephony-configurations/new?provider={provider}", status_code=303)
    session["flash"] = ("success", "Telephony configuration created.")
    return RedirectResponse(f"/telephony-configurations/{created.id}", status_code=303)


@rt("/telephony-configurations/{config_id}", methods=["GET"])
async def telephony_detail(session, config_id: int):
    return await _guard(session, "telephony", "Telephony configuration", lambda user: views.telephony_form_view(user, session, config_id=config_id))


@rt("/telephony-configurations/{config_id}", methods=["POST"])
async def telephony_update(session, config_id: int, name: str = "", provider: str = "", config_json: str = "", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse(f"/telephony-configurations/{config_id}", status_code=303)
    try:
        config = json.loads(config_json)
        request = TelephonyConfigurationUpdateRequest.model_validate({"name": name.strip(), "config": config})
        await update_telephony_configuration(config_id, request, user=user)
    except Exception as exc:
        session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
    else:
        session["flash"] = ("success", "Telephony configuration saved.")
    return RedirectResponse(f"/telephony-configurations/{config_id}", status_code=303)


@rt("/telephony-configurations/{config_id}/delete", methods=["POST"])
async def telephony_delete(session, config_id: int, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if _csrf_valid(session, csrf_token):
        try:
            await delete_telephony_configuration(config_id, user=user)
            session["flash"] = ("success", "Telephony configuration deleted.")
        except Exception as exc:
            session["flash"] = ("error", str(getattr(exc, "detail", None) or exc))
            return RedirectResponse(f"/telephony-configurations/{config_id}", status_code=303)
    else:
        session["flash"] = ("error", "Your session expired. Please try again.")
    return RedirectResponse("/telephony-configurations", status_code=303)


@rt("/reports", methods=["GET"])
async def reports(session, date: str = "", timezone: str = "Europe/Tallinn", workflow_id: str = ""):
    from datetime import date as date_type
    selected_date = date or date_type.today().isoformat()
    selected_workflow = int(workflow_id) if workflow_id.isdigit() else None
    return await _guard(session, "reports", "Reports", lambda user: views.reports_view(user, selected_date, timezone or "UTC", selected_workflow))


@rt("/api-keys", methods=["GET"])
async def api_keys(session):
    return await _guard(session, "api-keys", "API keys", lambda user: views.api_keys_view(user, session))


@rt("/api-keys", methods=["POST"])
async def api_keys_create(session, name: str = "", csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
        return RedirectResponse("/api-keys", status_code=303)
    created = await create_api_key_record(CreateAPIKeyRequest(name=name.strip() or "API key"), user=user)
    content = await views.api_keys_view(user, session, new_key=created)
    return app_shell(session, "api-keys", "API keys", *content)


@rt("/api-keys/{api_key_id}/archive", methods=["POST"])
async def api_keys_archive(session, api_key_id: int, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
    else:
        await archive_api_key_record(api_key_id, user=user)
        session["flash"] = ("success", "API key archived.")
    return RedirectResponse("/api-keys", status_code=303)


@rt("/api-keys/{api_key_id}/reactivate", methods=["POST"])
async def api_keys_reactivate(session, api_key_id: int, csrf_token: str = ""):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
    else:
        await reactivate_api_key_record(api_key_id, user=user)
        session["flash"] = ("success", "API key reactivated.")
    return RedirectResponse("/api-keys", status_code=303)


@rt("/settings", methods=["GET"])
async def settings(session):
    return await _guard(session, "settings", "Settings", lambda user: views.settings_view(user, session))


@rt("/settings", methods=["POST"])
async def settings_save(
    session,
    test_phone_number: str = "",
    timezone: str = "",
    external_pbx_integrations_enabled: str = "",
    csrf_token: str = "",
):
    user = await _user(session)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not _csrf_valid(session, csrf_token):
        session["flash"] = ("error", "Your session expired. Please try again.")
    else:
        await save_preferences(
            OrganizationPreferences(
                test_phone_number=test_phone_number.strip() or None,
                timezone=timezone.strip() or None,
                external_pbx_integrations_enabled=external_pbx_integrations_enabled == "true",
            ),
            user=user,
        )
        session["flash"] = ("success", "Organization preferences saved.")
    return RedirectResponse("/settings", status_code=303)


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
