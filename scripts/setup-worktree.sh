#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
PYTHON_VERSION="${PYTHON_VERSION:-3.13}"
VENV_PATH="$ROOT/.venv"
SENTINEL="$VENV_PATH/.worktree-setup-complete"

if [[ "${1:-}" == "--if-needed" && -f "$SENTINEL" ]]; then
  echo "FastVoice worktree is already provisioned."
  exit 0
fi

if [[ ! -x "$VENV_PATH/bin/python" ]]; then
  uv venv "$VENV_PATH" --python "$PYTHON_VERSION"
fi

uv pip install --python "$VENV_PATH/bin/python" -r api/requirements.txt
uv pip install --python "$VENV_PATH/bin/python" -r api/requirements.dev.txt
uv pip install --python "$VENV_PATH/bin/python" pytest pytest-asyncio pytest-cov ruff
touch "$SENTINEL"

echo "FastVoice worktree ready with $($VENV_PATH/bin/python -V)."
