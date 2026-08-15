"""Safe Python source projection for MCP workflow editing.

The bridge converts stored workflow JSON to a small, readable subset of the
FastVoice Python SDK and parses that subset back with :mod:`ast`.  Authored
source is never imported or executed.  Only imports, literal workflow/node
bindings, and ``workflow.edge(...)`` calls are accepted.
"""

from __future__ import annotations

import ast
import copy
import keyword
import pprint
import re
from typing import Any

from api.services.workflow.dto import EdgeDataDTO
from api.services.workflow.node_specs import all_specs
from api.services.workflow.node_specs._base import NodeSpec, PropertySpec, PropertyType


class PythonBridgeError(Exception):
    """A stored workflow could not be projected to safe Python source."""


def _class_name(spec_name: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", spec_name).split("_")
    return "".join(word[:1].upper() + word[1:] for word in words if word)


def _identifier(raw: str, used: set[str]) -> str:
    candidate = re.sub(r"\W+", "_", raw.strip().lower()).strip("_") or "node"
    if candidate[0].isdigit():
        candidate = f"n_{candidate}"
    if keyword.iskeyword(candidate) or candidate == "workflow":
        candidate = f"node_{candidate}"
    base = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _literal(value: Any) -> str:
    return pprint.pformat(value, width=92, sort_dicts=False, compact=False)


def _known_data(spec: NodeSpec, data: dict[str, Any]) -> dict[str, Any]:
    known = {prop.name: prop for prop in spec.properties}
    result: dict[str, Any] = {}
    for name, value in data.items():
        prop = known.get(name)
        if prop is None:
            continue
        if prop.type == PropertyType.fixed_collection and isinstance(value, list):
            row_names = {sub.name for sub in prop.properties or []}
            result[name] = [
                {key: item for key, item in row.items() if key in row_names}
                if isinstance(row, dict)
                else row
                for row in value
            ]
        else:
            result[name] = value
    return result


def _without_defaults(spec: NodeSpec, data: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        prop.name: prop.default
        for prop in spec.properties
        if prop.default is not None
    }
    return {
        name: value
        for name, value in data.items()
        if name not in defaults or defaults[name] != value
    }


async def generate_code(workflow: dict[str, Any], *, workflow_name: str = "") -> str:
    """Project workflow JSON to editable FastVoice Python SDK source."""
    specs = {spec.name: spec for spec in all_specs()}
    nodes = workflow.get("nodes") or []
    edges = workflow.get("edges") or []

    unknown = sorted({str(node.get("type")) for node in nodes if node.get("type") not in specs})
    if unknown:
        raise PythonBridgeError(f"Unknown node type in workflow: {', '.join(unknown)}")

    class_names = sorted({_class_name(str(node["type"])) for node in nodes})
    lines = ["from fastvoice_sdk import Workflow"]
    if class_names:
        lines.append(f"from fastvoice_sdk.typed import {', '.join(class_names)}")
    lines.extend(["", f"workflow = Workflow(name={workflow_name!r})", ""])

    used: set[str] = set()
    variables: dict[str, str] = {}
    for node in nodes:
        node_id = str(node.get("id", ""))
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        variable = _identifier(str(data.get("name") or f"node_{node_id}"), used)
        variables[node_id] = variable
        spec = specs[str(node["type"])]
        authored = _without_defaults(spec, _known_data(spec, data))
        args = ", ".join(f"{name}={_literal(value)}" for name, value in authored.items())
        node_expr = f"{_class_name(spec.name)}({args})"
        lines.append(f"{variable} = workflow.add_typed({node_expr})")

    edge_fields = set(EdgeDataDTO.model_fields)
    if edges:
        lines.append("")
    for edge in edges:
        source = variables.get(str(edge.get("source")))
        target = variables.get(str(edge.get("target")))
        if source is None or target is None:
            raise PythonBridgeError(
                f"Edge {edge.get('id', '<unknown>')} references an unknown node"
            )
        data = edge.get("data") if isinstance(edge.get("data"), dict) else {}
        options = {name: value for name, value in data.items() if name in edge_fields}
        args = ", ".join(f"{name}={_literal(value)}" for name, value in options.items())
        lines.append(f"workflow.edge({source}, {target}, {args})")

    return "\n".join(lines).rstrip() + "\n"


def _error(node: ast.AST | None, message: str) -> dict[str, Any]:
    item: dict[str, Any] = {"message": message}
    if node is not None and hasattr(node, "lineno"):
        item["line"] = node.lineno
        item["column"] = getattr(node, "col_offset", 0) + 1
    return item


def _literal_value(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError) as exc:
        raise ValueError("Only strings, numbers, booleans, None, lists, tuples, and dictionaries are allowed") from exc


def _call_name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _workflow_method(node: ast.AST, workflow_var: str | None) -> str | None:
    if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
        return None
    if workflow_var is not None and node.value.id != workflow_var:
        return None
    return node.attr


def _keywords(call: ast.Call, *, allow_starred: bool = False) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for kw in call.keywords:
        if kw.arg is None:
            raise ValueError("Dictionary expansion is not allowed")
        if kw.arg in values:
            raise ValueError(f"Duplicate keyword: {kw.arg}")
        values[kw.arg] = _literal_value(kw.value)
    if not allow_starred and any(isinstance(arg, ast.Starred) for arg in call.args):
        raise ValueError("Starred arguments are not allowed")
    return values


def _shape_name(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dictionary"
    return type(value).__name__


def _property_error(prop: PropertySpec, value: Any) -> str | None:
    string_types = {
        PropertyType.string,
        PropertyType.mention_textarea,
        PropertyType.url,
        PropertyType.recording_ref,
        PropertyType.credential_ref,
    }
    if prop.type in string_types:
        if not isinstance(value, str):
            return f"expected string, got {_shape_name(value)}"
        if prop.min_length is not None and len(value) < prop.min_length:
            return f"must contain at least {prop.min_length} characters"
        if prop.max_length is not None and len(value) > prop.max_length:
            return f"must contain at most {prop.max_length} characters"
        if prop.pattern is not None and re.search(prop.pattern, value) is None:
            return f"does not match required pattern {prop.pattern!r}"
        return None
    if prop.type == PropertyType.number:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"expected number, got {_shape_name(value)}"
        if prop.min_value is not None and value < prop.min_value:
            return f"must be at least {prop.min_value}"
        if prop.max_value is not None and value > prop.max_value:
            return f"must be at most {prop.max_value}"
        return None
    if prop.type == PropertyType.boolean:
        return None if isinstance(value, bool) else f"expected boolean, got {_shape_name(value)}"
    if prop.type == PropertyType.options:
        allowed = [option.value for option in prop.options or []]
        return None if not allowed or value in allowed else f"value {value!r} is not an allowed option"
    if prop.type in {PropertyType.tool_refs, PropertyType.document_refs, PropertyType.multi_options}:
        if not isinstance(value, list):
            return f"expected list, got {_shape_name(value)}"
        if prop.type == PropertyType.multi_options:
            allowed = [option.value for option in prop.options or []]
            if allowed and any(item not in allowed for item in value):
                return "contains a value that is not an allowed option"
        elif any(not isinstance(item, str) for item in value):
            return "list items must be strings"
        return None
    if prop.type == PropertyType.json:
        return None if isinstance(value, dict) else f"expected dictionary, got {_shape_name(value)}"
    if prop.type == PropertyType.fixed_collection:
        if not isinstance(value, list):
            return f"expected list of dictionaries, got {_shape_name(value)}"
        subprops = {sub.name: sub for sub in prop.properties or []}
        for index, row in enumerate(value):
            if not isinstance(row, dict):
                return f"row {index}: expected dictionary"
            unknown = set(row) - set(subprops)
            if unknown:
                return f"row {index}: unknown field {sorted(unknown)[0]!r}"
            for name, subprop in subprops.items():
                if name not in row:
                    if subprop.required and subprop.default is None:
                        return f"row {index}: missing required field {name!r}"
                    continue
                error = _property_error(subprop, row[name])
                if error:
                    return f"row {index}, {name!r}: {error}"
        return None
    return None


def _validate_data(spec: NodeSpec, data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    properties = {prop.name: prop for prop in spec.properties}
    unknown = set(data) - set(properties)
    if unknown:
        return None, f"Unknown field: {sorted(unknown)[0]!r}."

    result: dict[str, Any] = {}
    for name, prop in properties.items():
        if name in data:
            result[name] = data[name]
        elif prop.default is not None:
            result[name] = copy.deepcopy(prop.default)
        elif prop.required:
            return None, f"Missing required field: {name!r}."

    for name, value in result.items():
        error = _property_error(properties[name], value)
        if error:
            return None, f"Field {name!r}: {error}."
    return result, None


async def parse_code(code: str) -> dict[str, Any]:
    """Parse safe, literal-only Python SDK source into workflow JSON."""
    try:
        module = ast.parse(code, filename="workflow.py", mode="exec")
    except SyntaxError as exc:
        return {
            "ok": False,
            "stage": "parse",
            "errors": [{"message": exc.msg, "line": exc.lineno, "column": exc.offset}],
        }

    specs = {spec.name: spec for spec in all_specs()}
    types_by_class = {_class_name(name): name for name in specs}
    edge_fields = set(EdgeDataDTO.model_fields)
    errors: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    references: dict[str, dict[str, Any]] = {}
    workflow_var: str | None = None
    workflow_name = ""

    for statement in module.body:
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            continue
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
            if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
                call = statement.value
                if _workflow_method(call.func, workflow_var) != "edge":
                    errors.append(_error(statement, "Only workflow.edge(source, target, ...) calls are allowed as bare statements."))
                    continue
                if len(call.args) != 2 or not all(isinstance(arg, ast.Name) for arg in call.args):
                    errors.append(_error(call, "edge requires two previously bound node variables."))
                    continue
                source = references.get(call.args[0].id)
                target = references.get(call.args[1].id)
                if source is None or target is None:
                    errors.append(_error(call, "edge references an unknown node variable."))
                    continue
                try:
                    options = _keywords(call)
                except ValueError as exc:
                    errors.append(_error(call, str(exc)))
                    continue
                unknown = set(options) - edge_fields
                if unknown:
                    errors.append(_error(call, f"Unknown edge field: {sorted(unknown)[0]!r}."))
                    continue
                if not isinstance(options.get("label"), str) or not options["label"].strip():
                    errors.append(_error(call, "edge requires a non-empty label string."))
                    continue
                if not isinstance(options.get("condition"), str) or not options["condition"].strip():
                    errors.append(_error(call, "edge requires a non-empty condition string."))
                    continue
                edges.append({"id": f"{source['id']}-{target['id']}", "source": source["id"], "target": target["id"], "data": options})
                continue
            errors.append(_error(statement, "Only imports, simple bindings, and workflow.edge(...) calls are allowed at the top level."))
            continue

        variable = statement.targets[0].id
        call = statement.value
        if not isinstance(call, ast.Call):
            errors.append(_error(statement, "Bindings must call Workflow, workflow.add_typed, or workflow.add."))
            continue

        if _call_name(call.func) == "Workflow":
            if workflow_var is not None:
                errors.append(_error(statement, "Only one Workflow binding is allowed."))
                continue
            if call.args:
                errors.append(_error(call, "Workflow accepts keyword arguments only in MCP-authored source."))
                continue
            try:
                values = _keywords(call)
            except ValueError as exc:
                errors.append(_error(call, str(exc)))
                continue
            unknown = set(values) - {"name", "description"}
            if unknown or ("name" in values and not isinstance(values["name"], str)):
                errors.append(_error(call, "Workflow accepts literal name and description strings only."))
                continue
            workflow_var = variable
            workflow_name = values.get("name", "")
            continue

        method = _workflow_method(call.func, workflow_var)
        node_type: str | None = None
        data: dict[str, Any] = {}
        position = {"x": 0.0, "y": 0.0}
        try:
            if method == "add_typed":
                if len(call.args) != 1 or not isinstance(call.args[0], ast.Call):
                    raise ValueError("add_typed requires one typed node constructor.")
                constructor = call.args[0]
                class_name = _call_name(constructor.func)
                node_type = types_by_class.get(class_name or "")
                if node_type is None:
                    raise ValueError(f"Unknown typed node class: {class_name or '<expression>'}.")
                if constructor.args:
                    raise ValueError("Typed node constructors accept keyword arguments only.")
                data = _keywords(constructor)
                call_options = _keywords(call)
                if set(call_options) - {"position"}:
                    raise ValueError("add_typed accepts only the position keyword.")
                raw_position = call_options.get("position")
            elif method == "add":
                if call.args:
                    raise ValueError("add accepts keyword arguments only.")
                values = _keywords(call)
                node_type = values.pop("type", None)
                raw_position = values.pop("position", None)
                data = values
                if not isinstance(node_type, str) or node_type not in specs:
                    raise ValueError(f"Unknown node type: {node_type!r}.")
            else:
                raise ValueError("Workflow must be created before nodes; use workflow.add_typed(...) or workflow.add(...).")
            if raw_position is not None:
                if not isinstance(raw_position, (list, tuple)) or len(raw_position) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in raw_position):
                    raise ValueError("position must be a two-number tuple or list.")
                position = {"x": float(raw_position[0]), "y": float(raw_position[1])}
        except ValueError as exc:
            errors.append(_error(call, str(exc)))
            continue

        node = {"id": str(len(nodes) + 1), "type": node_type, "position": position, "data": data}
        nodes.append(node)
        references[variable] = node

    if errors:
        return {"ok": False, "stage": "parse", "errors": errors}
    if workflow_var is None:
        return {"ok": False, "stage": "parse", "errors": [{"message": "No Workflow construction found. Expected: workflow = Workflow(name='...')."}]}

    validation_errors: list[dict[str, Any]] = []
    for node in nodes:
        validated, error = _validate_data(specs[node["type"]], node["data"])
        if error:
            validation_errors.append({"message": f"[{node['type']}] {error}"})
        else:
            node["data"] = validated
    if validation_errors:
        return {"ok": False, "stage": "validate", "errors": validation_errors}

    return {
        "ok": True,
        "workflow": {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 1}},
        "workflowName": workflow_name,
    }
