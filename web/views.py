"""Authenticated FastVoice FastHTML views backed by the retained API services."""
# ruff: noqa: F403, F405 - FastHTML's element DSL is intentionally exported.
from __future__ import annotations

import json
from typing import Any

from fasthtml.common import *

from api.routes.campaign import get_campaign, get_campaign_runs, get_campaigns
from api.routes.knowledge_base import list_documents
from api.routes.node_types import list_node_types
from api.routes.organization import (
    get_preferences,
    get_model_configuration_v2,
    get_model_configuration_v2_defaults,
    get_telephony_providers_metadata,
    get_telephony_configuration_by_id,
    list_telephony_configurations,
)
from api.routes.user import get_api_keys
from api.routes.tool import get_tool, list_tools
from api.routes.workflow import get_workflow, get_workflow_count, get_workflows
from api.routes.workflow_recording import list_recordings
from api.routes.reports import get_daily_report, get_workflow_options
from api.routes.workflow_embed import get_embed_token
from web.components import csrf_input, data_table, empty_state, format_time, metric, page_header, status_badge


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


async def campaign_new_view(user, session):
    workflows = await get_workflows(user=user, status="active")
    configs_response = await list_telephony_configurations(user=user)
    configs = list(_get(configs_response, "configurations", []))
    return (
        page_header("Operate", "New campaign", "Upload a CSV containing a phone_number column and choose a published voice agent."),
        Section(
            Form(
                csrf_input(session),
                Label("Campaign name", Input(name="name", required=True, maxlength=255, autofocus=True)),
                Label("Voice agent", Select(*[Option(_get(w, "name", "Workflow"), value=str(_get(w, "id"))) for w in workflows], name="workflow_id", required=True)),
                Label("Telephony configuration", Select(*[Option(_get(c, "name", "Configuration"), value=str(_get(c, "id"))) for c in configs], name="telephony_configuration_id", required=bool(configs))),
                Label("Contact CSV", Input(name="source_file", type="file", accept=".csv,text/csv", required=True)),
                Small("Maximum 10 MB. Columns become initial_context values available to workflow nodes."),
                Label("Maximum concurrent calls", Input(name="max_concurrency", type="number", min="1", max="100", value="1")),
                Details(
                    Summary("Retry controls"),
                    Label("Maximum retries", Input(name="max_retries", type="number", min="0", max="10", value="2")),
                    Label("Delay between retries (seconds)", Input(name="retry_delay_seconds", type="number", min="30", max="3600", value="120")),
                ),
                Div(A("Cancel", href="/campaigns", cls="quiet-button"), Button("Create campaign", type="submit", cls="primary-action"), cls="form-actions"),
                method="post",
                action="/campaigns/new",
                enctype="multipart/form-data",
                cls="stack-form",
            ),
            cls="panel form-panel",
        ),
    )


async def campaign_detail_view(user, campaign_id: int, session):
    campaign = await get_campaign(campaign_id, user=user)
    runs_response = await get_campaign_runs(campaign_id, page=1, limit=50, filters=None, sort_by=None, sort_order="desc", user=user)
    runs = list(_get(runs_response, "runs", []))
    state = str(_get(campaign, "state", "created"))
    actions = []
    if state in {"created", "scheduled"}:
        actions.append(("start", "Start campaign"))
    if state == "running":
        actions.append(("pause", "Pause"))
    if state == "paused":
        actions.append(("resume", "Resume"))
    action_forms = [
        Form(csrf_input(session), Button(label, type="submit", cls="primary-action" if action in {"start", "resume"} else "secondary-action"), method="post", action=f"/campaigns/{campaign_id}/{action}")
        for action, label in actions
    ]
    run_rows = [
        (
            _get(run, "id", "—"),
            status_badge(_get(run, "state", _get(run, "status", "unknown"))),
            format_time(_get(run, "created_at")),
            format_time(_get(run, "completed_at")),
            _get(run, "disposition_code", "—") or "—",
        )
        for run in runs
    ]
    logs = list(_get(campaign, "logs", []))
    return (
        page_header("Campaign", _get(campaign, "name", "Campaign"), f"{_get(campaign, 'workflow_name', 'Unknown workflow')} · {_get(campaign, 'telephony_configuration_name', 'Default telephony')}", Div(*action_forms, cls="page-actions")),
        Div(
            metric("Status", str(state).replace("_", " ").title()),
            metric("Progress", f"{_get(campaign, 'executed_count', 0)} / {_get(campaign, 'total_queued_count', 0)}"),
            metric("Processed", _get(campaign, "processed_rows", 0)),
            metric("Failed", _get(campaign, "failed_rows", 0)),
            cls="metrics-grid",
        ),
        Section(Div(H2("Runs"), A("Download CSV report", href=f"/api/v1/campaign/{campaign_id}/report", cls="text-action"), cls="section-head"), data_table(("Run", "Status", "Started", "Completed", "Disposition"), run_rows) if run_rows else empty_state("No calls yet", "Start the campaign to queue its contact rows."), cls="panel"),
        Section(H2("Campaign log"), *[Article(Strong(_get(entry, "event", "Event")), P(_get(entry, "message", "")), Small(_get(entry, "ts", "")), cls="log-entry") for entry in logs], cls="panel") if logs else None,
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


async def tool_form_view(user, session, tool_uuid: str | None = None, *, test_result=None):
    tool = await get_tool(tool_uuid, user=user) if tool_uuid else None
    definition = _get(tool, "definition", None) or {
        "schema_version": 1,
        "type": "http_api",
        "config": {
            "method": "POST",
            "url": "https://api.example.com/action",
            "parameters": [{"name": "query", "type": "string", "description": "The value to send", "required": True}],
            "timeout_ms": 5000,
        },
    }
    category = _get(tool, "category", definition.get("type", "http_api"))
    title = _get(tool, "name", "New tool")
    result_panel = None
    if test_result is not None:
        result_panel = Section(H2("Test result"), Pre(Code(json.dumps(_plain(test_result), indent=2, default=str))), cls="panel")
    controls = None
    if tool is not None:
        archived = str(_get(tool, "status", "")) == "archived"
        controls = Div(
            Form(csrf_input(session), Button("Restore tool" if archived else "Archive tool", type="submit", cls="secondary-action"), method="post", action=f"/tools/{tool_uuid}/{'unarchive' if archived else 'archive'}"),
            cls="page-actions",
        )
    return (
        page_header("Extend", title, "Configure typed tool behavior as JSON. The schema is validated by FastVoice before it can be used by an agent.", controls),
        result_panel,
        Section(
            Form(
                csrf_input(session),
                Label("Name", Input(name="name", value=_get(tool, "name", "") or "", required=True, maxlength=255)),
                Label("Description", Textarea(_get(tool, "description", "") or "", name="description", rows=3)),
                Label("Category", Select(*[Option(value.replace("_", " ").title(), value=value, selected=value == category) for value in ("http_api", "mcp", "calculator", "end_call", "transfer_call")], name="category")),
                Label("Definition", Textarea(json.dumps(definition, indent=2), name="definition_json", rows=20, spellcheck="false", cls="code-editor")),
                Div(A("Cancel", href="/tools", cls="quiet-button"), Button("Save tool", type="submit", cls="primary-action"), cls="form-actions"),
                method="post",
                action=f"/tools/{tool_uuid}" if tool_uuid else "/tools/new",
                cls="stack-form",
            ),
            cls="panel form-panel",
        ),
        Section(
            H2("Test HTTP tool"),
            Form(
                csrf_input(session),
                Label("Model parameters (JSON)", Textarea("{}", name="llm_params_json", rows=6, cls="code-editor")),
                Label("Preset parameters (JSON)", Textarea("{}", name="preset_params_json", rows=4, cls="code-editor")),
                Button("Run test", type="submit", cls="secondary-action"),
                method="post",
                action=f"/tools/{tool_uuid}/test",
                cls="stack-form",
            ),
            cls="panel form-panel",
        ) if tool_uuid and category == "http_api" and str(_get(tool, "status", "")) != "archived" else None,
    )


async def files_view(user, session):
    response = await list_documents(status=None, limit=100, offset=0, user=user)
    docs = list(_get(response, "documents", []))
    table = data_table(
        ("Document", "Status", "Chunks", "Retrieval", "Updated", ""),
        [(_get(d, "filename", "Document"), status_badge(_get(d, "processing_status")), _get(d, "total_chunks", 0), _get(d, "retrieval_mode", "—"), format_time(_get(d, "updated_at")), Form(csrf_input(session), Button("Delete", type="submit", cls="table-action"), method="post", action=f"/files/{_get(d, 'document_uuid')}/delete")) for d in docs],
    )
    return (
        page_header("Ground", "Knowledge", "Upload documents agents can retrieve during live conversations."),
        Section(
            H2("Upload a document"),
            Form(
                csrf_input(session),
                Label("File", Input(name="document_file", type="file", required=True)),
                Label("Retrieval mode", Select(Option("Chunked vector search", value="chunked"), Option("Full document", value="full_document"), name="retrieval_mode")),
                Button("Upload and process", type="submit", cls="primary-action"),
                method="post", action="/files/upload", enctype="multipart/form-data", cls="inline-form",
            ),
            cls="panel form-panel",
        ),
        Section(table if docs else empty_state("No knowledge documents", "Upload a PDF, text file or supported document to ground your agents."), cls="panel"),
    )


async def recordings_view(user, session):
    response = await list_recordings(workflow_id=None, tts_provider=None, tts_model=None, tts_voice_id=None, user=user)
    recordings = list(_get(response, "recordings", []))
    table = data_table(
        ("ID", "Provider", "Voice", "Transcript", "Created", ""),
        [(_get(r, "recording_id", "Recording"), _get(r, "tts_provider", "—") or "—", _get(r, "tts_voice_id", "—") or "—", (_get(r, "transcript", "") or "")[:80], format_time(_get(r, "created_at")), Form(csrf_input(session), Button("Delete", type="submit", cls="table-action"), method="post", action=f"/recordings/{_get(r, 'recording_id')}/delete")) for r in recordings],
    )
    return (
        page_header("Media", "Recordings", "Manage reusable speech and uploaded audio for workflow nodes."),
        Section(
            H2("Upload recording"),
            Form(
                csrf_input(session),
                Label("Audio file", Input(name="audio_file", type="file", accept="audio/*", required=True)),
                Label("Transcript", Textarea(name="transcript", rows=3, required=True, placeholder="Words spoken in this recording")),
                Button("Upload recording", type="submit", cls="primary-action"),
                method="post", action="/recordings/upload", enctype="multipart/form-data", cls="inline-form",
            ),
            cls="panel form-panel",
        ),
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
    saved_response = await list_telephony_configurations(user=user)
    saved = list(_get(saved_response, "configurations", []))
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
        Section(
            H2("Configurations"),
            data_table(("Name", "Provider", "Numbers", "Default", "Updated", ""), [(_get(c, "name", "Configuration"), str(_get(c, "provider", "")).upper(), _get(c, "phone_number_count", 0), "Yes" if _get(c, "is_default_outbound") else "—", format_time(_get(c, "updated_at")), A("Configure", href=f"/telephony-configurations/{_get(c, 'id')}", cls="table-action")) for c in saved]) if saved else empty_state("No telephony configurations", "Add a provider account before making or receiving phone calls."),
            cls="panel",
        ),
        H2("Available providers"),
        Div(*cards, cls="resource-grid") if cards else empty_state("No providers available", "Telephony provider metadata could not be loaded."),
    )


async def telephony_form_view(user, session, config_id: int | None = None, provider: str | None = None):
    metadata = await get_telephony_providers_metadata(user=user)
    providers = list(_get(metadata, "providers", []))
    current = await get_telephony_configuration_by_id(config_id, user=user) if config_id else None
    selected_provider = _get(current, "provider", provider or (_get(providers[0], "provider", "twilio") if providers else "twilio"))
    credentials = dict(_get(current, "credentials", {}) or {})
    credentials["provider"] = selected_provider
    if not current:
        spec = next((item for item in providers if _get(item, "provider") == selected_provider), None)
        for field in list(_get(spec, "fields", [])):
            name = _get(field, "name")
            if name and name not in credentials:
                credentials[name] = ""
    return (
        page_header("Connect", _get(current, "name", "New telephony configuration"), "Provider credentials are encrypted at rest; sensitive values are masked after save."),
        Section(
            Form(
                csrf_input(session),
                Label("Configuration name", Input(name="name", value=_get(current, "name", "") or "", required=True, maxlength=64)),
                Label("Provider", Select(*[Option(_get(item, "display_name", _get(item, "provider")), value=_get(item, "provider"), selected=_get(item, "provider") == selected_provider) for item in providers], name="provider", disabled=bool(current))),
                Label("Provider configuration (JSON)", Textarea(json.dumps(credentials, indent=2), name="config_json", rows=20, spellcheck="false", cls="code-editor")),
                Label(Input(name="is_default_outbound", type="checkbox", value="true", checked=bool(_get(current, "is_default_outbound"))), " Use as default outbound configuration", cls="checkbox-line"),
                Div(A("Cancel", href="/telephony-configurations", cls="quiet-button"), Button("Save configuration", type="submit", cls="primary-action"), cls="form-actions"),
                method="post", action=f"/telephony-configurations/{config_id}" if config_id else "/telephony-configurations/new", cls="stack-form",
            ),
            cls="panel form-panel",
        ),
        Section(Form(csrf_input(session), Button("Delete configuration", type="submit", cls="secondary-action"), method="post", action=f"/telephony-configurations/{config_id}/delete"), cls="panel danger-panel") if current else None,
    )


async def api_keys_view(user, session, *, new_key=None):
    keys = await get_api_keys(include_archived=True, user=user)
    rows = []
    for key in keys:
        active = bool(_get(key, "is_active")) and not _get(key, "archived_at")
        action = Form(
            csrf_input(session),
            Button("Archive" if active else "Reactivate", type="submit", cls="table-action"),
            method="post",
            action=f"/api-keys/{_get(key, 'id')}/{'archive' if active else 'reactivate'}",
        )
        rows.append((
            _get(key, "name", "API key"),
            Code(f"{_get(key, 'key_prefix', '')}…"),
            status_badge("active" if active else "archived"),
            format_time(_get(key, "last_used_at")),
            format_time(_get(key, "created_at")),
            action,
        ))
    revealed = None
    if new_key is not None:
        revealed = Section(
            Span("Copy this key now", cls="eyebrow"),
            H2("Your new API key"),
            P("FastVoice stores only its hash. This value will not be shown again."),
            Div(Code(_get(new_key, "api_key", ""), id="new-api-key"), Button("Copy", type="button", data_copy_target="new-api-key", cls="secondary-action"), cls="secret-reveal"),
            cls="panel secret-panel",
        )
    return (
        page_header("Integrate", "API keys", "Create revocable organization keys for the REST API and Python SDK."),
        revealed,
        Section(
            H2("Create an API key"),
            Form(
                csrf_input(session),
                Label("Key name", Input(name="name", required=True, maxlength=120, placeholder="Production automation")),
                Button("Create key", type="submit", cls="primary-action"),
                method="post",
                action="/api-keys",
                cls="inline-form",
            ),
            cls="panel form-panel",
        ),
        Section(data_table(("Name", "Prefix", "Status", "Last used", "Created", ""), rows) if rows else empty_state("No API keys", "Create a key for the Python SDK or direct API access."), cls="panel"),
    )


async def settings_view(user, session):
    preferences = await get_preferences(user=user)
    timezone = _get(preferences, "timezone", "") or ""
    return (
        page_header("Workspace", "Settings", "Manage organization defaults used by tests, campaigns and telephony."),
        Section(
            H2("Organization preferences"),
            Form(
                csrf_input(session),
                Label("Test phone number", Input(name="test_phone_number", type="tel", value=_get(preferences, "test_phone_number", "") or "", placeholder="+372…")),
                Label("Timezone", Input(name="timezone", value=timezone, placeholder="Europe/Tallinn")),
                Label(Input(name="external_pbx_integrations_enabled", type="checkbox", value="true", checked=bool(_get(preferences, "external_pbx_integrations_enabled"))), " Enable external PBX integrations", cls="checkbox-line"),
                Button("Save preferences", type="submit", cls="primary-action"),
                method="post",
                action="/settings",
                cls="stack-form",
            ),
            cls="panel form-panel",
        ),
    )


async def reports_view(user, date: str, timezone: str, workflow_id: int | None = None):
    options = await get_workflow_options(user=user)
    report = await get_daily_report(date=date, timezone=timezone, workflow_id=workflow_id, user=user)
    metrics_data = dict(_get(report, "metrics", {}) or {})
    metrics = [metric(key.replace("_", " ").title(), value) for key, value in metrics_data.items()]
    dispositions = list(_get(report, "disposition_distribution", []))
    durations = list(_get(report, "call_duration_distribution", []))
    return (
        page_header("Analyse", "Reports", "Review daily call volume, outcomes and duration distributions."),
        Section(
            Form(
                Label("Date", Input(name="date", type="date", value=date)),
                Label("Timezone", Input(name="timezone", value=timezone)),
                Label("Voice agent", Select(Option("All agents", value=""), *[Option(_get(w, "name", "Workflow"), value=str(_get(w, "id")), selected=_get(w, "id") == workflow_id) for w in options], name="workflow_id")),
                Button("Apply", type="submit", cls="primary-action"),
                method="get", action="/reports", cls="inline-form",
            ),
            cls="panel form-panel",
        ),
        Div(*metrics, cls="metrics-grid") if metrics else empty_state("No calls", "No workflow runs matched this reporting window."),
        Div(
            Section(H2("Dispositions"), data_table(("Disposition", "Calls"), [(_get(item, "disposition", _get(item, "name", "Unknown")), _get(item, "count", 0)) for item in dispositions]) if dispositions else empty_state("No dispositions", "Call outcomes appear after completed runs."), cls="panel"),
            Section(H2("Call duration"), data_table(("Range", "Calls"), [(_get(item, "range", _get(item, "bucket", "Unknown")), _get(item, "count", 0)) for item in durations]) if durations else empty_state("No duration data", "Call durations appear after completed runs."), cls="panel"),
            cls="two-column-grid",
        ),
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
    embed_token = await get_embed_token(workflow_id, request=None, user=user)
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
                A("Preview", href=f"/workflow/{workflow_id}/preview", cls="quiet-button") if embed_token else None,
                Form(csrf_input(session), Button("Duplicate", type="submit", cls="quiet-button"), method="post", action=f"/workflow/{workflow_id}/duplicate"),
                Form(csrf_input(session), Button("Restore" if _get(workflow, "status") == "archived" else "Archive", type="submit", cls="quiet-button"), Input(type="hidden", name="status", value="active" if _get(workflow, "status") == "archived" else "archived"), method="post", action=f"/workflow/{workflow_id}/status"),
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
        Section(
            Div(H2("Web widget"), P("Create one scoped token for browser voice and chat embeds.")),
            (
                Div(
                    Textarea(_get(embed_token, "embed_script", ""), rows=10, readonly=True, id="embed-script", cls="code-editor"),
                    Div(Button("Copy embed code", type="button", data_copy_target="embed-script", cls="secondary-action"), A("Open preview", href=f"/workflow/{workflow_id}/preview", cls="primary-action"), cls="form-actions"),
                    Form(csrf_input(session), Button("Deactivate token", type="submit", cls="quiet-button"), method="post", action=f"/workflow/{workflow_id}/embed-token/deactivate"),
                )
                if embed_token
                else Form(csrf_input(session), Button("Create embed token", type="submit", cls="primary-action"), method="post", action=f"/workflow/{workflow_id}/embed-token")
            ),
            cls="panel embed-panel",
        ),
    )
