#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "FastVoice virtual environment not found. Create .venv first." >&2
  exit 1
fi

export PYTHONPATH="$REPO_ROOT/sdk/python/src:$REPO_ROOT"

echo "Generating typed workflow nodes..."
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

from api.services.workflow.node_specs import all_specs
from fastvoice_sdk.codegen import generate_all

generate_all(
    [spec.model_dump(mode="json") for spec in all_specs()],
    Path("sdk/python/src/fastvoice_sdk/typed"),
)
PY

echo "Generating filtered OpenAPI and Python client models..."
"$PYTHON_BIN" -m api.scripts.dump_sdk_openapi --output /tmp/fastvoice-sdk-openapi.json
"$PYTHON_BIN" -m datamodel_code_generator \
  --input /tmp/fastvoice-sdk-openapi.json \
  --input-file-type openapi \
  --output sdk/python/src/fastvoice_sdk/_generated_models.py \
  --output-model-type pydantic_v2.BaseModel \
  --use-standard-collections \
  --use-union-operator
"$PYTHON_BIN" sdk/codegen/client_codegen.py \
  --input /tmp/fastvoice-sdk-openapi.json \
  --py-out sdk/python/src/fastvoice_sdk/_generated_client.py

echo "FastVoice Python SDK generated."
