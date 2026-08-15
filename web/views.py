"""Authenticated FastVoice FastHTML views backed by the retained API services."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fasthtml.common import *

from api.routes.campaign import get_campaigns
from api.routes.knowledge_base import list_documents
from api.routes.node_types import list_node_types
from api.routes.organization import (
    get_model_configuration_v2,
    get_model_configuration_v2_defaults,
    get_telephony_providers_metadata,
)
from api.routes.tool import list_tools
from api.routes.workflow import get_workflow, get_workflow_count, get_workflows
from api.routes.workflow_recording import list_recordings
from web.components import data_table, empty_state, format_time, metric, page_header, status_badge


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


async def overview_view(user):
    counts = await get_workflow_count(user=user)
    campaigns = await get_campaigns(user=user)
    tools = await list_tools(user=user)
    recent = await get_workflows(user=user, status=None)
    campaign_items = list(_get(campaigns, "campaigns", []))
    return (
        page_header("Workspace", "Overview", "Build, test and operate every voice workflow from one place.", A("New voice agent", href="/workflow/create", cls="primary-action")),
        Div(
            metric("Voice agents", _get(counts, "total", 0), f"{_get(counts, 'active', 0)} active"),
            metric("Campaigns", len(campaign_items), "Outbound operations"),
            metric("Tools", len(tools), "Reusable actions"),
            metric("Provider mode", "BYOK", "Your keys, your infrastructure"),
            cls="metrics-grid",
        ),
        Section(
            Div(H2("Recent voice agents"), A("View all", href="/workflow"), cls="section-head"),
            workflow_table(recent[:6]) if recent else empty_state("Create your first voice agent", "Start with a simple greeting, add an agent node, then test the conversation in your browser.", A("Create voice agent", href="/workflow/create", cls="primary-action")),
            cls="panel",
        ),
    )


def workflow_table(workflows):
    return data_table(
        ("Name", "Status", "Runs", "Created", ""),
        [
            (
                A(_get(w, "name", "Untitled"), href=f"/workflow/{_get(w, 'id')}"),
                status_badge(_get(w, "status")),
                _get(w, "total_runs", 0),
                format_time(_get(w, "created_at")),
                A("Open", href=f"/workflow/{_get(w, 'id')}", cls="table-action"),
            )
            for w in workflows
        ],
    )


async def workflows_view(user, status: str | None = None):
    workflows = await get_workflows(user=user, status=status)
    return (
        page_header("Build", "Voice agents", "Design workflows, test drafts and publish production versions.", A("New voice agent", href="/workflow/create", cls="primary-action")),
        Div(
            A("All", href="/workflow", cls="filter-chip active" if not status else "filter-chip"),
            A("Active", href="/workflow?status=active", cls="filter-chip active" if status == "active" else "filter-chip"),
            A("Archived", href="/workflow?status=archived", cls="filter-chip active" if status == "archived" else "filter-chip"),
            cls="filter-row",
        ),
        Section(workflow_table(workflows) if workflows else empty_state("No voice agents here", "Create a workflow or change the current status filter."), cls="panel"),
    )


async def campaigns_view(user):
    response = await get_campaigns(user=user)
    campaigns = list(_get(response, "campaigns", []))
    table = data_table(
        ("Campaign", "Workflow", "Status", "Progress", "Created", ""),
        [
            (
                A(_get(c, "name", "Campaign"), href=f"/campaigns/{_get(c, 'id')}"),
                _get(c, "workflow_name", "—"),
                status_badge(_get(c, "status")),
                f"{_get(c, 'executed_count', 0)} / {_get(c, 'total_queued_count', 0)}",
                format_time(_get(c, "created_at")),
                A("Open", href=f"/campaigns/{_get(c, 'id')}", cls="table-action"),
            ) for c in campaigns
        ],
    )
    return (
        page_header("Operate", "Campaigns", "Schedule and monitor outbound conversations with clear safeguards.", A("New campaign", href="/campaigns/new", cls="primary-action")),
        Section(table if campaigns else empty_state("No campaigns yet", "Create an outbound campaign from a published voice agent."), cls="panel"),
    )


async def tools_view(user):
    tools = await list_tools(user=user)
    cards = [
        Article(
            Div(status_badge(_get(tool, "status")), Span(str(_get(tool, "category", "tool")).replace("_", " ").title(), cls="card-meta"), cls="card-head"),
            H3(_get(tool, "name", "Untitled tool")),
            P(_get(tool, "description", "No description provided.")),
            A("Configure tool", href=f"/tools/{_get(tool, 'uuid')}", cls="text-action"),
            cls="resource-card",
        ) for tool in tools
    ]
    return (
        page_header("Extend", "Tools", "Give agents safe access to HTTP APIs, built-in actions and MCP servers.", A("New tool", href="/tools/new", cls="primary-action")),
        Div(*cards, cls="resource-grid") if cards else empty_state("No tools configured", "Add a reusable action, HTTP API call or MCP integration."),
    )


async def files_view(user):
    response = await list_documents(status=None, limit=100, offset=0, user=user)
    docs = list(_get(response, "documents", []))
    table = data_table(
        ("Document", "Status", "Chunks", "Retrieval", "Updated"),
        [(_get(d, "filename", "Document"), status_badge(_get(d, "processing_status")), _get(d, "total_chunks", 0), _get(d, "retrieval_mode", "—"), format_time(_get(d, "updated_at"))) for d in docs],
    )
    return (
        page_header("Ground", "Knowledge", "Upload documents agents can retrieve during live conversations.", Button("Upload document", type="button", cls="primary-action", data_dialog_open="upload-document")),
        Section(table if docs else empty_state("No knowledge documents", "Upload a PDF, text file or supported document to ground your agents."), cls="panel"),
    )


async def recordings_view(user):
    response = await list_recordings(workflow_id=None, tts_provider=None, tts_model=None, tts_voice_id=None, user=user)
    recordings = list(_get(response, "recordings", []))
    table = data_table(
        ("Name", "Provider", "Voice", "Duration", "Created"),
        [(_get(r, "name", _get(r, "filename", "Recording")), _get(r, "tts_provider", "—"), _get(r, "tts_voice_id", "—"), f"{_get(r, 'duration_seconds', 0)}s", format_time(_get(r, "created_at"))) for r in recordings],
    )
    return (
        page_header("Media", "Recordings", "Manage reusable speech and uploaded audio for workflow nodes.", Button("Add recording", type="button", cls="primary-action")),
        Section(table if recordings else empty_state("No recordings", "Create speech from a configured voice or upload an audio file."), cls="panel"),
    )


async def models_view(user, session):
    defaults = await get_model_configuration_v2_defaults(user=user)
    current = await get_model_configuration_v2(user=user)
    pipeline = defaults["byok"]["pipeline"]
    groups = []
    for key, title in (("llm", "Language models"), ("stt", "Speech to text"), ("tts", "Text to speech"), ("embeddings", "Embeddings")):
        providers = pipeline.get(key, {})
        groups.append(Article(Span(str(len(providers)), cls="provider-count"), H3(title), P(", ".join(name.replace("_", " ").title() for name in providers) or "No providers"), cls="resource-card"))
    realtime = defaults["byok"]["realtime"].get("realtime", {})
    groups.append(Article(Span(str(len(realtime)), cls="provider-count"), H3("Realtime voice"), P(", ".join(name.replace("_", " ").title() for name in realtime)), cls="resource-card feature-card"))
    source = _get(current, "source", "default")
    return (
        page_header("Intelligence", "Model configurations", "Choose global defaults for pipeline or realtime voice, then override individual agents."),
        Div(Span("Effective source"), status_badge(source), cls="context-strip"),
        Section(
            Div(
                Span("xAI", cls="eyebrow"),
                H2("Connect Grok realtime voice"),
                P("Use the server's configured xAI key, or paste a different key. FastVoice validates it directly with xAI and masks it in every API response."),
            ),
            Form(
                csrf_input(session),
                Label("xAI API key", Input(name="api_key", type="password", autocomplete="off", placeholder="Leave blank to use the server key")),
                Label("Realtime model", Input(name="realtime_model", value="grok-voice-think-fast-1.0", required=True)),
                Label("Voice", Select(Option("Ara", value="ara"), Option("Eve", value="eve"), Option("Rex", value="rex"), Option("Sal", value="sal"), Option("Leo", value="leo"), name="voice")),
                Label("Assistant model", Input(name="llm_model", value="grok-4-fast-reasoning", required=True)),
                Button("Save and validate xAI", type="submit", cls="primary-action"),
                method="post",
                action="/model-configurations/xai",
                cls="stack-form model-quick-connect",
            ),
            cls="panel form-panel",
        ),
        Div(*groups, cls="resource-grid"),
    )


async def telephony_view(user):
    metadata = await get_telephony_providers_metadata(user=user)
    providers = list(_get(metadata, "providers", []))
    cards = [
        Article(
            Span(_get(p, "provider", "provider").upper(), cls="card-meta"),
            H3(_get(p, "display_name", _get(p, "provider", "Provider"))),
            P(f"{len(_get(p, 'fields', []))} configuration fields"),
            A("Configure", href=f"/telephony-configurations/new?provider={_get(p, 'provider')}", cls="text-action"),
            cls="resource-card",
        ) for p in providers
    ]
    return (
        page_header("Connect", "Telephony", "Bring phone numbers and SIP providers into inbound and outbound workflows.", A("New configuration", href="/telephony-configurations/new", cls="primary-action")),
        Div(*cards, cls="resource-grid") if cards else empty_state("No providers available", "Telephony provider metadata could not be loaded."),
    )


async def node_catalog_view(user):
    result = await list_node_types(_user=user)
    specs = list(_get(result, "node_types", []))
    return Div(*[Article(Span(_get(s, "category", "node"), cls="card-meta"), H3(_get(s, "display_name", _get(s, "name", "Node"))), P(_get(s, "description", "")), cls="resource-card") for s in specs], cls="resource-grid")


def simple_view(eyebrow: str, title: str, body: str):
    return page_header(eyebrow, title, body), Section(empty_state(title, body), cls="panel")


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: _plain(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return value


async def workflow_editor_view(user, workflow_id: int, session: dict[str, Any]):
    workflow = await get_workflow(workflow_id, user=user)
    catalog = await list_node_types(_user=user)
    specs = list(_get(catalog, "node_types", []))
    payload = {
        "workflow": _plain(workflow),
        "specs": _plain(specs),
    }
    safe_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return (
        Link(rel="stylesheet", href="/static/css/workflow-editor.css"),
        Script(src="/static/js/workflow-editor.js", defer=True),
        Script(NotStr(safe_json), id="workflow-editor-data", type="application/json"),
        Header(
            Div(
                A("Voice agents", href="/workflow", cls="back-link"),
                Div(
                    Input(
                        value=_get(workflow, "name", "Untitled agent"),
                        id="workflow-name",
                        aria_label="Workflow name",
                    ),
                    Span(
                        f"Version {_get(workflow, 'version_number', '—')} · {_get(workflow, 'version_status', 'published')}",
                        cls="editor-version",
                    ),
                ),
                cls="editor-title",
            ),
            Div(
                Button("Fit", type="button", cls="quiet-button", id="fit-workflow"),
                Button("Add node", type="button", cls="secondary-action", id="add-node"),
                Form(
                    csrf_input(session),
                    Button("Publish", type="submit", cls="secondary-action"),
                    method="post",
                    action=f"/workflow/{workflow_id}/publish",
                    id="publish-workflow-form",
                ),
                Button("Save draft", type="button", cls="primary-action", id="save-workflow"),
                cls="editor-actions",
            ),
            cls="workflow-editor-header",
        ),
        Div(
            Aside(
                Div(
                    H2("Nodes"),
                    P("Drag nodes on the canvas. Select one to edit its fields."),
                    cls="editor-panel-head",
                ),
                Div(id="node-list", cls="node-list"),
                cls="editor-rail editor-rail-left",
            ),
            Section(
                Div(
                    Svg(id="workflow-edges", cls="workflow-edges"),
                    Div(id="workflow-nodes", cls="workflow-nodes"),
                    cls="workflow-stage",
                    id="workflow-stage",
                ),
                Div(
                    Button("−", type="button", id="zoom-out", aria_label="Zoom out"),
                    Span("100%", id="zoom-label"),
                    Button("+", type="button", id="zoom-in", aria_label="Zoom in"),
                    cls="zoom-controls",
                ),
                cls="workflow-canvas",
            ),
            Aside(
                Div(H2("Properties"), P("Select a node to configure it."), cls="editor-panel-head"),
                Div(id="property-editor", cls="property-editor"),
                Div(
                    H3("Transitions"),
                    Div(id="edge-list", cls="edge-list"),
                    Button("Add transition", type="button", cls="secondary-action wide", id="add-edge"),
                    cls="edge-editor",
                ),
                cls="editor-rail editor-rail-right",
            ),
            cls="workflow-editor",
        ),
        Form(
            csrf_input(session),
            Input(type="hidden", name="name", id="save-workflow-name"),
            Textarea(name="workflow_json", id="save-workflow-json"),
            method="post",
            action=f"/workflow/{workflow_id}/save",
            id="save-workflow-form",
            hidden=True,
        ),
        Dialog(
            Form(
                H2("Add node"),
                Label("Node type", Select(id="new-node-type")),
                Div(
                    Button("Cancel", type="button", cls="quiet-button", id="cancel-add-node"),
                    Button("Add to canvas", type="button", cls="primary-action", id="confirm-add-node"),
                    cls="dialog-actions",
                ),
                method="dialog",
            ),
            id="add-node-dialog",
        ),
    )
