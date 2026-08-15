"""Regression coverage for the authenticated FastHTML route surface."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import web.app as web_app
from web import views


ERROR_MARKER = "This view could not be loaded:"


@pytest.fixture()
def authenticated_web(monkeypatch):
    user = SimpleNamespace(
        id=1,
        email="route-test@example.com",
        provider_id="route-test",
        selected_organization_id=1,
    )

    async def current_user(_session):
        return user

    monkeypatch.setattr(web_app, "_user", current_user)

    responses = {
        "get_workflow_count": {"total": 0, "active": 0},
        "get_campaigns": {"campaigns": []},
        "list_tools": [],
        "get_workflows": [],
        "list_telephony_configurations": {"configurations": []},
        "get_campaign": {"id": 1, "name": "Route campaign", "state": "created"},
        "get_campaign_runs": {"runs": []},
        "get_tool": {
            "uuid": "route-tool",
            "name": "Route tool",
            "category": "http_api",
            "status": "active",
            "definition": {"type": "http_api", "config": {}},
        },
        "list_documents": {"documents": []},
        "list_recordings": {"recordings": []},
        "get_model_configuration_v2_defaults": {
            "byok": {
                "pipeline": {"llm": {}, "stt": {}, "tts": {}, "embeddings": {}},
                "realtime": {"realtime": {}},
            }
        },
        "get_model_configuration_v2": {"source": "default"},
        "get_telephony_providers_metadata": {"providers": []},
        "get_telephony_configuration_by_id": {
            "id": 1,
            "name": "Route telephony",
            "provider": "twilio",
            "credentials": {},
        },
        "get_api_keys": [],
        "get_preferences": {},
        "get_workflow_options": [],
        "get_daily_report": {},
        "get_workflow": {
            "id": 1,
            "name": "Route workflow",
            "status": "active",
            "version_number": 1,
            "version_status": "draft",
        },
        "get_embed_token": None,
        "list_node_types": {"node_types": []},
    }
    for name, response in responses.items():
        monkeypatch.setattr(views, name, AsyncMock(return_value=response))

    monkeypatch.setattr(
        web_app,
        "get_embed_token",
        AsyncMock(return_value=SimpleNamespace(token="route-preview-token")),
    )
    monkeypatch.setattr(
        web_app,
        "get_workflow_record",
        AsyncMock(return_value=SimpleNamespace(id=1, name="Route workflow")),
    )
    return TestClient(web_app.app, raise_server_exceptions=True)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/overview", "Overview"),
        ("/workflow", "Voice agents"),
        ("/workflow/create", "New voice agent"),
        ("/workflow/1", "Route workflow"),
        ("/workflow/1/preview", "Browser test"),
        ("/campaigns", "New campaign"),
        ("/campaigns/new", "Contact CSV"),
        ("/campaigns/1", "Route campaign"),
        ("/tools", "Tools"),
        ("/tools/new", "Definition"),
        ("/tools/route-tool", "Route tool"),
        ("/files", "Upload a document"),
        ("/recordings", "Upload recording"),
        ("/model-configurations", "Connect Grok realtime voice"),
        ("/telephony-configurations", "Available providers"),
        ("/telephony-configurations/new", "Provider configuration"),
        ("/telephony-configurations/1", "Route telephony"),
        ("/reports", "Reports"),
        ("/api-keys", "Create an API key"),
        ("/settings", "Organization preferences"),
    ],
)
def test_authenticated_get_routes_render_without_guarded_errors(
    authenticated_web, path, expected
):
    response = authenticated_web.get(path, follow_redirects=False)

    assert response.status_code == 200, path
    assert ERROR_MARKER not in response.text, path
    assert expected in response.text, path
