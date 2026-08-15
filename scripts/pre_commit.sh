#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"

"$REPO_ROOT/scripts/format.sh"
PYTHONPATH=sdk/python/src:. "$PYTHON_BIN" -m pytest \
  api/tests/test_python_only_tree.py \
  api/tests/test_python_bridge.py \
  api/tests/test_mcp_save_workflow.py \
  api/tests/test_sdk_sync.py
