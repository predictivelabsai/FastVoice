"""MCP tool that accepts LLM-authored FastVoice SDK Python and creates a workflow.

Companion to `save_workflow`: where `save_workflow` updates an existing
workflow as a new draft, `create_workflow` brings a workflow into being
in one shot. The resulting workflow is published as version 1 — there
is no prior published version to protect, so we skip the draft step.

Execution flow mirrors `save_workflow`:
    1. Parse with Python's AST — the authored source is never executed.
    2. Pydantic validation via `WorkflowGraphDTO.model_validate`.
    3. Graph and resolved custom-tool name validation.
    4. Persist via `db_client.create_workflow` — workflow row + v1
       published definition in a single transaction.

Each failure path returns an `error_code` via `_error_result`. Those
codes and their meanings are documented in the `create_workflow`
docstring (the description shipped to the LLM via `tools/list`); keep the
two in sync — `test_mcp_instructions_drift.py` enforces it.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import ValidationError as PydanticValidationError

from api.db import db_client
from api.db.agent_trigger_client import TriggerPathConflictError
from api.enums import PostHogEvent
from api.mcp_server.auth import authenticate_mcp_request
from api.mcp_server.tracing import traced_tool
from api.mcp_server.python_bridge import PythonBridgeError, parse_code
from api.services.posthog_client import capture_event
from api.services.workflow.dto import WorkflowGraphDTO
from api.services.workflow.layout import reconcile_positions
from api.services.workflow.tool_name_validation import (
    validate_workflow_tool_name_collisions,
)
from api.services.workflow.trigger_paths import (
    extract_trigger_paths,
    validate_trigger_paths,
)
from api.services.workflow.workflow_graph import WorkflowGraph


def _error_result(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"created": False, "error_code": code, "error": message, **extra}


def _format_errors(errors: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for e in errors:
        loc = ""
        line = e.get("line")
        col = e.get("column")
        if line is not None:
            loc = f" (line {line}" + (f", col {col}" if col is not None else "") + ")"
        parts.append(f"{e.get('message', '')}{loc}")
    return "\n".join(parts)


@traced_tool
async def create_workflow(code: str) -> dict[str, Any]:
    """Parse FastVoice SDK Python and create a new published workflow.

    `code` is literal-only Python source using `fastvoice_sdk`. The workflow
    name comes from `Workflow(name="...")` and is required.

    Example code:
        from fastvoice_sdk import Workflow
        from fastvoice_sdk.typed import StartCall, EndCall

        workflow = Workflow(name="lead_qualification")
        greeting = workflow.add_typed(StartCall(name="Greeting", prompt="Hi!"))
        done = workflow.add_typed(EndCall(name="Done", prompt="Bye."))
        workflow.edge(greeting, done, label="done", condition="conversation complete")

    On success the new workflow is published as version 1. Use
    `save_workflow(workflow_id, code)` for subsequent edits — those go to
    a draft.

    On failure the result has `created: false`, a machine-readable
    `error_code`, and a human-readable `error` (with file:line:column
    where the problem is locatable). Resubmit the full corrected source —
    patches are not accepted. Possible `error_code` values:
    - `parse_error` — disallowed construct or malformed Python.
    - `validation_error` — node data failed spec validation (unknown
      field, missing required, wrong type, option out of range).
    - `schema_validation` — wire-format (DTO) rejection; rare.
    - `graph_validation` — structural rule broken (e.g. no start node,
      unreachable node, edge to/from the wrong node type).
    - `missing_name` — `new Workflow({ name })` is absent or empty; the
      name is required and there is no prior workflow to fall back to.
    - `trigger_path_conflict` — a trigger node's path is already used by
      another workflow in this organization; rename it and resubmit.
    - `bridge_error` — internal/transient; retry once, then surface it.
    """
    user = await authenticate_mcp_request()

    # 1. Parse and spec-validate with the safe Python AST bridge.
    try:
        parsed = await parse_code(code)
    except PythonBridgeError as e:
        logger.warning(f"python_bridge failure: {e}")
        return _error_result("bridge_error", str(e))

    if not parsed.get("ok"):
        stage = parsed.get("stage", "parse")
        errs = parsed.get("errors") or []
        code_key = "parse_error" if stage == "parse" else "validation_error"
        return _error_result(code_key, _format_errors(errs), errors=errs)

    payload = parsed["workflow"]
    name = (parsed.get("workflowName") or "").strip()
    if not name:
        return _error_result(
            "missing_name",
            'Workflow name is required. Add `workflow = Workflow(name="...")` to the source.',
        )

    # 1b. New workflow — no prior version to reconcile against; layout
    # places new nodes adjacent to their first incoming neighbor.
    payload = reconcile_positions(payload, None)
    trigger_path_issues = validate_trigger_paths(payload)
    if trigger_path_issues:
        return _error_result(
            "validation_error",
            "\n".join(issue.message for issue in trigger_path_issues),
        )

    # 2. Pydantic shape check (defence in depth — parser is spec-driven).
    try:
        dto = WorkflowGraphDTO.model_validate(payload)
    except PydanticValidationError as e:
        return _error_result("schema_validation", str(e))

    # 3. Graph-level semantic validation (start-node count, edge shape).
    try:
        WorkflowGraph(dto)
    except (ValueError, Exception) as e:  # WorkflowGraph raises ValueError
        return _error_result("graph_validation", str(e))

    tool_name_errors = await validate_workflow_tool_name_collisions(
        payload,
        user.selected_organization_id,
    )
    if tool_name_errors:
        return _error_result(
            "graph_validation",
            "\n".join(error["message"] for error in tool_name_errors),
            errors=tool_name_errors,
        )

    # 4. Reject upfront if any trigger path collides with another workflow's
    # trigger in this org so we don't leave an orphan workflow record.
    trigger_paths = extract_trigger_paths(payload)
    if trigger_paths:
        try:
            await db_client.assert_trigger_paths_available(
                trigger_paths=trigger_paths,
            )
        except TriggerPathConflictError as e:
            return _error_result(
                "trigger_path_conflict", str(e), trigger_paths=e.trigger_paths
            )

    # 5. Persist as a new workflow with v1 published.
    workflow = await db_client.create_workflow(
        name,
        payload,
        user.id,
        user.selected_organization_id,
    )

    capture_event(
        distinct_id=str(user.provider_id),
        event=PostHogEvent.WORKFLOW_CREATED,
        properties={
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            "source": "mcp",
            "organization_id": user.selected_organization_id,
        },
    )

    if trigger_paths:
        await db_client.sync_triggers_for_workflow(
            workflow_id=workflow.id,
            organization_id=user.selected_organization_id,
            trigger_paths=trigger_paths,
        )

    return {
        "created": True,
        "workflow_id": workflow.id,
        "name": workflow.name,
        "status": workflow.status,
        "version_number": 1,
        "node_count": len(payload["nodes"]),
        "edge_count": len(payload["edges"]),
    }
