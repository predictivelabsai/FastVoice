# FastVoice

FastVoice is a self-hosted voice-agent platform built with Python, FastHTML,
HTMX, and browser-native JavaScript. It combines a visual workflow editor,
live browser testing, outbound campaigns, telephony, knowledge retrieval,
tools, recordings, model configuration, REST APIs, MCP, and a typed Python SDK
in one deployable application.

Production: [voice.fastsme.com](https://voice.fastsme.com)

## What changed from Dograh

FastVoice is a maintained port of the open-source
[Dograh](https://github.com/dograh-hq/dograh) backend. The Python voice runtime,
provider integrations, database model, workers, and public API are retained.
The separate frontend and its build/runtime toolchain have been replaced by:

- server-rendered FastHTML pages;
- HTMX request/response flows;
- a browser-native workflow canvas and WebRTC controls;
- a literal-only Python AST bridge for MCP workflow authoring;
- the `fastvoice_sdk` Python package and Python-only examples;
- a single application image serving pages, API, MCP, assets, and sockets.

Managed upstream cloud dependencies are not part of the FastVoice product
surface. FastVoice is designed for bring-your-own provider keys and
self-hosted infrastructure.

## Architecture

```text
Browser
  └─ FastHTML + HTMX + native JavaScript
       └─ FastAPI application (:8000)
            ├─ workflow, campaign, telephony, tool, and knowledge APIs
            ├─ MCP workflow authoring over safe Python source
            ├─ Pipecat voice pipelines and WebRTC
            ├─ ARQ background workers
            └─ Postgres/pgvector · Redis · MinIO
```

Python 3.13 is the primary development runtime. Postgres with pgvector, Redis,
and MinIO run as Docker backing services. Production is deployed through
GitHub-to-Coolify CI/CD at `voice.fastsme.com`.

## Local development

Prerequisites: Python 3.13, `uv`, Docker Engine with Compose, and FFmpeg.

```bash
docker compose -f docker-compose-local.yaml up -d
python -m venv .venv
uv pip install --python .venv/bin/python -r api/requirements.txt
cp api/.env.example api/.env
```

Set strong values for `OSS_JWT_SECRET` and `FASTVOICE_SESSION_SECRET`, then set
provider credentials such as `XAI_API_KEY` in the ignored environment file.
Run migrations and the development server:

```bash
set -a; source api/.env; set +a
.venv/bin/alembic -c api/alembic.ini upgrade head
.venv/bin/uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Open <http://localhost:8000>. API documentation is at
<http://localhost:8000/api/v1/docs>.

## Python SDK

```bash
uv pip install -e sdk/python
```

```python
from fastvoice_sdk import FastVoiceClient, Workflow

with FastVoiceClient(
    base_url="https://voice.fastsme.com",
    api_key="fv_...",
) as client:
    workflow = Workflow(client=client, name="lead_qualification")
    start = workflow.add(
        type="startCall",
        name="Greeting",
        prompt="Greet the caller and ask how you can help.",
    )
    done = workflow.add(
        type="endCall",
        name="Done",
        prompt="Thank the caller and say goodbye.",
    )
    workflow.edge(
        start,
        done,
        label="complete",
        condition="the caller's request has been resolved",
    )
```

Runnable programs live in [`examples/python`](examples/python).

## Authentication

FastVoice supports local email/password accounts and Google OpenID Connect.
The production callback is:

```text
https://voice.fastsme.com/auth/google/callback
```

Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and optionally
`GOOGLE_ALLOWED_DOMAINS` or `GOOGLE_ALLOWED_EMAILS`.

## Upstream synchronization

The `upstream` Git remote points to `dograh-hq/dograh`. Imported Python changes
are reviewed and ported periodically; frontend changes are reimplemented in
FastHTML or native JavaScript rather than merged directly.

```bash
git fetch upstream main
git log --oneline --left-right main...upstream/main
```

The initial port is based on upstream commit
`66ab884d5e4098d37beef7bc502a422ef42951ee` (2026-08-14).

## Tests

```bash
PYTHONPATH=sdk/python/src:. .venv/bin/python -m pytest api/tests
```

The repository also enforces that no frontend-language source or its package
toolchain enters the tracked tree.

## Licensing and attribution

New FastVoice-specific work is available under the MIT License in
[`LICENSE`](LICENSE). Code derived from Dograh remains under its BSD 2-Clause
license in [`LICENSES/Dograh-BSD-2-Clause.txt`](LICENSES/Dograh-BSD-2-Clause.txt).
See [`NOTICE`](NOTICE) for provenance. Third-party dependencies retain their
own licenses.
