# FastVoice contributor guide

FastVoice is a Python 3.13 application. Public and authenticated pages use
FastHTML, enhanced interactions use HTMX, and the workflow canvas/WebRTC layer
uses browser-native JavaScript. Do not introduce a frontend package toolchain.

Key directories:

- `api/` — retained voice runtime, REST API, workers, providers, and migrations
- `web/` — FastHTML routes, authentication, page views, and components
- `static/` — CSS and browser-native JavaScript
- `sdk/python/` — typed FastVoice Python SDK
- `examples/python/` — supported examples
- `deploy/` — deployment templates

Use `apply_patch` for edits, run `scripts/pre_commit.sh` before committing, and
preserve the BSD attribution for code derived from Dograh. The `upstream`
remote is for review and deliberate ports; never merge its old frontend tree.
