"""Contract tests for the literal-only FastVoice Python workflow bridge."""

from __future__ import annotations

import pytest

from api.mcp_server.python_bridge import PythonBridgeError, generate_code, parse_code


def _workflow() -> dict:
    return {
        "nodes": [
            {
                "id": "1",
                "type": "startCall",
                "position": {"x": 20, "y": 30},
                "data": {"name": "Greeting", "prompt": "Welcome the caller."},
            },
            {
                "id": "2",
                "type": "endCall",
                "position": {"x": 300, "y": 30},
                "data": {"name": "Done", "prompt": "Say goodbye."},
            },
        ],
        "edges": [
            {
                "id": "1-2",
                "source": "1",
                "target": "2",
                "data": {"label": "done", "condition": "the caller is finished"},
            }
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


@pytest.mark.asyncio
async def test_generate_and_parse_round_trip() -> None:
    code = await generate_code(_workflow(), workflow_name="demo")
    assert "from fastvoice_sdk import Workflow" in code
    assert "workflow.add_typed(StartCall(" in code
    assert "workflow.edge(greeting, done" in code

    parsed = await parse_code(code)
    assert parsed["ok"] is True
    assert parsed["workflowName"] == "demo"
    assert [node["type"] for node in parsed["workflow"]["nodes"]] == [
        "startCall",
        "endCall",
    ]
    assert len(parsed["workflow"]["edges"]) == 1


@pytest.mark.asyncio
async def test_generic_add_is_supported() -> None:
    parsed = await parse_code(
        """from fastvoice_sdk import Workflow
workflow = Workflow(name="demo")
start = workflow.add(type="startCall", name="Start", prompt="Hello")
"""
    )
    assert parsed["ok"] is True
    assert parsed["workflow"]["nodes"][0]["type"] == "startCall"


@pytest.mark.asyncio
async def test_unknown_field_is_validation_error() -> None:
    parsed = await parse_code(
        """from fastvoice_sdk import Workflow
from fastvoice_sdk.typed import StartCall
workflow = Workflow(name="demo")
start = workflow.add_typed(StartCall(prompt="Hello", promt="typo"))
"""
    )
    assert parsed["ok"] is False
    assert parsed["stage"] == "validate"
    assert "Unknown field" in parsed["errors"][0]["message"]


@pytest.mark.asyncio
async def test_runtime_code_is_rejected_without_execution(tmp_path) -> None:
    marker = tmp_path / "must-not-exist"
    parsed = await parse_code(
        f"""from fastvoice_sdk import Workflow
workflow = Workflow(name="demo")
value = open({str(marker)!r}, "w")
"""
    )
    assert parsed["ok"] is False
    assert not marker.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [
        "workflow = Workflow(name=f'{1}')",
        "workflow = Workflow(name='demo')\nfor item in []:\n    pass",
        "workflow = Workflow(name='demo')\ndef build():\n    pass",
        "workflow = Workflow(name='demo')\nvalue = [x for x in []]",
    ],
)
async def test_dynamic_constructs_are_rejected(source: str) -> None:
    parsed = await parse_code(source)
    assert parsed["ok"] is False
    assert parsed["stage"] == "parse"


@pytest.mark.asyncio
async def test_edge_requires_bound_nodes() -> None:
    parsed = await parse_code(
        """from fastvoice_sdk import Workflow
workflow = Workflow(name="demo")
workflow.edge(missing, other, label="x", condition="y")
"""
    )
    assert parsed["ok"] is False
    assert "unknown node" in parsed["errors"][0]["message"]


@pytest.mark.asyncio
async def test_generate_rejects_unknown_node_type() -> None:
    payload = _workflow()
    payload["nodes"][0]["type"] = "inventedNode"
    with pytest.raises(PythonBridgeError, match="Unknown node type"):
        await generate_code(payload)
