"""Integration tests for MCP draft saves through the safe Python bridge."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.mcp_server.tools.save_workflow import save_workflow


@dataclass
class _FakeDraft:
    version_number: int = 2
    status: str = "draft"


class _FakeWorkflowModel:
    id = 1
    organization_id = 1
    name = "test"
    current_definition = None
    released_definition = None
    workflow_definition = None


@pytest.fixture
def authed_user() -> MagicMock:
    user = MagicMock()
    user.selected_organization_id = 1
    user.id = 1
    return user


@pytest.fixture
def mock_backends(authed_user: MagicMock):
    save_mock = AsyncMock(return_value=_FakeDraft())
    update_mock = AsyncMock(return_value=_FakeWorkflowModel())
    with (
        patch("api.mcp_server.tools.save_workflow.authenticate_mcp_request", AsyncMock(return_value=authed_user)),
        patch("api.mcp_server.tools.save_workflow.db_client.get_workflow", AsyncMock(return_value=_FakeWorkflowModel())),
        patch("api.mcp_server.tools.save_workflow.db_client.save_workflow_draft", save_mock),
        patch("api.mcp_server.tools.save_workflow.db_client.update_workflow", update_mock),
        patch("api.mcp_server.tools.save_workflow.db_client.get_draft_version", AsyncMock(return_value=None)),
    ):
        yield save_mock, update_mock


def _valid_code(name: str = "test") -> str:
    return f'''from fastvoice_sdk import Workflow
from fastvoice_sdk.typed import StartCall, EndCall

workflow = Workflow(name={name!r})
greeting = workflow.add_typed(StartCall(name="greeting", prompt="Hi!"))
done = workflow.add_typed(EndCall(name="done", prompt="Bye."))
workflow.edge(greeting, done, label="done", condition="conversation complete")
'''


@pytest.mark.asyncio
async def test_happy_path_saves_draft(mock_backends):
    save_mock, update_mock = mock_backends
    result = await save_workflow(1, _valid_code())
    assert result["saved"] is True
    assert result["node_count"] == 2
    assert result["edge_count"] == 1
    assert result["renamed"] is False
    save_mock.assert_awaited_once()
    update_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_updates_workflow(mock_backends):
    save_mock, update_mock = mock_backends
    result = await save_workflow(1, _valid_code("renamed"))
    assert result["saved"] is True
    assert result["renamed"] is True
    assert result["name"] == "renamed"
    update_mock.assert_awaited_once()
    save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_dynamic_top_level_code_is_rejected(mock_backends):
    save_mock, _ = mock_backends
    result = await save_workflow(1, _valid_code() + "\nfor item in []:\n    pass\n")
    assert result["saved"] is False
    assert result["error_code"] == "parse_error"
    save_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_typed_node_is_rejected(mock_backends):
    save_mock, _ = mock_backends
    code = """from fastvoice_sdk import Workflow
workflow = Workflow(name="x")
node = workflow.add_typed(InventedNode(name="x"))
"""
    result = await save_workflow(1, code)
    assert result["error_code"] == "parse_error"
    assert "Unknown typed node" in result["error"]
    save_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_field_is_validation_error(mock_backends):
    save_mock, _ = mock_backends
    code = """from fastvoice_sdk import Workflow
from fastvoice_sdk.typed import StartCall
workflow = Workflow(name="x")
node = workflow.add_typed(StartCall(name="g", prompt="hi", promt="typo"))
"""
    result = await save_workflow(1, code)
    assert result["error_code"] == "validation_error"
    assert "Unknown field" in result["error"]
    save_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_validation_requires_start_node(mock_backends):
    save_mock, _ = mock_backends
    code = """from fastvoice_sdk import Workflow
from fastvoice_sdk.typed import EndCall
workflow = Workflow(name="orphan")
done = workflow.add_typed(EndCall(name="done", prompt="Bye."))
"""
    result = await save_workflow(1, code)
    assert result["error_code"] == "graph_validation"
    save_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_transition_labels_fail_graph_validation(mock_backends):
    save_mock, _ = mock_backends
    code = """from fastvoice_sdk import Workflow
from fastvoice_sdk.typed import StartCall, EndCall
workflow = Workflow(name="duplicate")
start = workflow.add_typed(StartCall(name="start", prompt="Hi."))
first = workflow.add_typed(EndCall(name="first", prompt="Bye."))
second = workflow.add_typed(EndCall(name="second", prompt="Bye."))
workflow.edge(start, first, label="handoff", condition="caller wants sales")
workflow.edge(start, second, label="handoff", condition="caller wants support")
"""
    result = await save_workflow(1, code)
    assert result["error_code"] == "graph_validation"
    assert "duplicated" in result["error"]
    save_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_workflow_is_404(authed_user: MagicMock):
    with (
        patch("api.mcp_server.tools.save_workflow.authenticate_mcp_request", AsyncMock(return_value=authed_user)),
        patch("api.mcp_server.tools.save_workflow.db_client.get_workflow", AsyncMock(return_value=None)),
    ):
        with pytest.raises(HTTPException) as exc:
            await save_workflow(999, _valid_code())
    assert exc.value.status_code == 404
