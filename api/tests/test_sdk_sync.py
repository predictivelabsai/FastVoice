"""Drift guard: committed SDK typed files must match what codegen
produces from the current `node_specs/` registry.

Fails loudly if a spec was edited without running
`./scripts/generate_sdk.sh`. CI also runs the full script and asserts
an empty `git diff` as the authoritative generated-code check; this
test is the fast local feedback loop inside pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the Python SDK package is importable without requiring a
# `pip install -e sdk/python`. The codegen lives there because it ships
# with the SDK wheel, but tests need to reach it directly.
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_PY_SRC = REPO_ROOT / "sdk" / "python" / "src"
if str(SDK_PY_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_PY_SRC))

from fastvoice_sdk.codegen import generate_all  # noqa: E402

from api.services.workflow.node_specs import SPEC_VERSION, all_specs  # noqa: E402

PY_OUT = REPO_ROOT / "sdk" / "python" / "src" / "fastvoice_sdk" / "typed"
REGEN_HINT = "Run ./scripts/generate_sdk.sh to regenerate."


def _specs_payload() -> dict:
    return {
        "spec_version": SPEC_VERSION,
        "node_types": [s.model_dump(mode="json") for s in all_specs()],
    }


def _compare_trees(expected_dir: Path, actual_dir: Path, *, skip: set[str]) -> None:
    def tree(d: Path) -> dict[str, str]:
        return {
            p.name: p.read_text()
            for p in d.iterdir()
            if p.is_file() and p.name not in skip
        }

    expected = tree(expected_dir)
    actual = tree(actual_dir)

    if expected.keys() != actual.keys():
        pytest.fail(
            f"File set differs in {expected_dir.name}/.\n"
            f"  committed: {sorted(expected)}\n"
            f"  generated: {sorted(actual)}\n"
            f"{REGEN_HINT}"
        )
    for name in sorted(expected):
        if expected[name] != actual[name]:
            pytest.fail(
                f"{expected_dir.name}/{name} is out of sync with node_specs. "
                f"{REGEN_HINT}"
            )


def test_python_sdk_typed_in_sync(tmp_path: Path) -> None:
    specs = _specs_payload()["node_types"]
    generate_all(specs, tmp_path)
    # _base.py is hand-written and lives alongside generated files.
    _compare_trees(PY_OUT, tmp_path, skip={"_base.py", "__pycache__"})
