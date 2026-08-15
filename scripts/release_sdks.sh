#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
"$REPO_ROOT/scripts/generate_sdk.sh"
PYTHONPATH=sdk/python/src:. "$PYTHON_BIN" -m pytest \
  api/tests/test_fastvoice_sdk.py \
  api/tests/test_fastvoice_sdk_typed.py \
  api/tests/test_sdk_sync.py

rm -rf sdk/python/dist
"$PYTHON_BIN" -m build sdk/python
"$PYTHON_BIN" -m twine check sdk/python/dist/*

echo "Artifacts are ready in sdk/python/dist/."
echo "Publish after review with: $PYTHON_BIN -m twine upload sdk/python/dist/*"
