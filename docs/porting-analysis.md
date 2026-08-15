---
title: FastVoice porting analysis
description: Architecture, parity, deployment, and upstream-maintenance record for the FastVoice port.
---

# FastVoice porting analysis

Updated: 2026-08-15  
Dograh baseline: `66ab884d5e4098d37beef7bc502a422ef42951ee` (v1.45.0)

## Objective and decisions

FastVoice is the self-hosted, Python-first port of Dograh for the FastSME
stack. The agreed constraints are:

- run Python natively during development with containerized backing services;
- deploy the complete stack through Coolify at `voice.fastsme.com`;
- support local email/password authentication and Google OpenID Connect;
- retain open-source backend, voice-runtime, API, provider, telephony, MCP,
  worker, and Python SDK behavior;
- remove managed Dograh cloud, billing, and hosted-service dependencies from
  the reachable product surface;
- do not track or ship TypeScript, TSX, Node package manifests, or a frontend
  build/runtime toolchain;
- keep `dograh-hq/dograh` as the `upstream` Git remote and review Python changes
  periodically.

## Source inventory

The imported baseline contained roughly 147,000 lines of Python and 72,700
lines of TypeScript/TSX. It exposed 168 OpenAPI operations, 31 Next.js page
entries, 709 Python modules, and 375 TypeScript/TSX modules. The retained API
suite contains 185 test modules and approximately 1,565 test functions.

The FastVoice tree contains no tracked `.ts` or `.tsx` files, package manager
lockfiles, `package.json`, or `tsconfig` files. Browser behavior that cannot be
expressed as an HTML response—WebRTC, the embeddable widget, canvas dragging,
and small interaction helpers—is plain browser JavaScript served as a static
asset.

## Resulting architecture

```text
Browser
  ├─ public FastSME landing page
  ├─ FastHTML application pages and forms
  ├─ HTMX-compatible partial/request conventions
  ├─ native-JavaScript workflow canvas
  └─ native-JavaScript WebRTC/chat embed widget
       │
       ▼
FastAPI + FastHTML process
  ├─ local and Google OIDC authentication
  ├─ workflow, call, campaign, report and provider APIs
  ├─ WebRTC, WebSocket and telephony entry points
  ├─ safe Python-source MCP workflow bridge
  ├─ ARQ workers and campaign orchestration
  └─ Python SDK contract
       │
       ├─ PostgreSQL 17 + pgvector
       ├─ Redis
       └─ MinIO
```

Production adds a small Nginx gateway image for HTTP/WebSocket routing. Its
configuration is copied into the image, so Coolify does not depend on host
bind mounts or a Node build stage.

## Functional parity map

| Capability | FastVoice implementation |
| --- | --- |
| Public site | FastHTML landing page, product narrative, developer entry point, SEO metadata, sitemap, robots and favicon |
| Authentication | Local sign-up/sign-in, signed sessions, CSRF, replay-safe FastSME suite SSO backed by FastOffice Google OIDC, allowlisted emails/domains |
| Voice agents | List/filter/create, native canvas editor, typed node catalogue, transitions, draft save, publish, duplicate, archive/restore |
| Browser testing | Scoped embed-token management and an authenticated microphone/chat preview page |
| Embed distribution | Rebranded browser-native floating, inline and headless widget plus generated embed code |
| Campaigns | CSV upload and validation, workflow/telephony selection, retry/concurrency controls, start/pause/resume, run history and CSV reports |
| Tools | List/create/update/archive/restore, typed schema validation, HTTP execution test and MCP refresh through the retained API |
| Knowledge | Upload, storage, queued document processing, retrieval mode, status/chunk listing and deletion |
| Recordings | Audio upload, transcript metadata, storage-backed listing and deletion |
| Models | BYOK provider catalogue and one-step xAI realtime voice plus OpenAI-compatible Grok LLM configuration |
| Telephony | Provider catalogue, multi-configuration list/create/update/delete and masked credential round trips |
| Reports | Daily workflow filters, metrics, dispositions and call-duration distributions |
| API keys | Local hashed organization API keys, one-time reveal, archive and restore |
| Settings | Test number, timezone and external-PBX organization preferences |
| API/MCP/SDK | Retained versioned REST API and MCP surface; Python-only `fastvoice_sdk` and examples |

Complex tool and telephony provider payloads use validated JSON editors in the
FastHTML UI. This preserves every provider-specific field without generating a
second client schema or introducing a frontend compiler.

## Managed-service removal

Organization bootstrap is local and idempotent. Managed service-key and usage
routers are not mounted. Hosted billing, managed Cloudonix defaults, natural
language workflow generation through MPS, and the hosted transcription proxy
are not part of the reachable FastVoice UI. Provider credentials are BYOK;
uploaded-file transcription returns an explicit `501` until it can use the
same configured STT contract as live calls.

Compatibility module and constant names are retained where changing them would
create unnecessary merge conflicts with upstream Python. They are not exposed
as FastVoice product branding.

## xAI validation

The existing ignored xAI credential in the FastCo sister repositories was
copied only into ignored/runtime environment storage. It was never printed or
committed. The credential successfully authenticated against xAI's model and
TTS voice endpoints, and production receives it through Coolify's encrypted
environment store.

## Verification record

- Python compilation succeeds across the port.
- All three browser JavaScript assets pass syntax parsing.
- Local and Coolify Compose configurations parse successfully.
- Focused MCP bridge, MCP server, SDK, no-TypeScript and embed checks: 48 pass.
- Authentication, local bootstrap and workflow slice: 12 pass.
- Additional authentication/security regression slice after CRUD completion:
  18 pass.
- The full collected upstream suite: 1,776 pass; remaining failures/errors
  require local PostgreSQL, Redis or MinIO services, or assert retired managed
  cloud behavior.
- Production health, landing, API docs, robots, sitemap, embed asset and
  OpenAPI endpoints return HTTP 200 over a valid certificate.
- A Chromium production smoke test reports no console errors or warnings.

## Upstream maintenance

Python updates are reviewed from `upstream/main`. Database, voice-runtime,
provider and API changes can be ported normally. TypeScript/TSX changes are
treated as behavior specifications and reimplemented in FastHTML or native
browser JavaScript. Managed-service changes are evaluated only for compatible
self-hosted behavior.

The normal review command is:

```bash
git fetch upstream main
git log --oneline --left-right main...upstream/main
```

Before each upstream sync, run the no-TypeScript tree check, focused port tests,
Compose validation and a production browser smoke test.
