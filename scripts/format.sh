#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"

"$PYTHON_BIN" -m ruff format api web sdk/python/src sdk/codegen examples/python
"$PYTHON_BIN" -m ruff check --fix api web sdk/python/src sdk/codegen examples/python
