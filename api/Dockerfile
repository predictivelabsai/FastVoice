# syntax=docker/dockerfile:1
# FastVoice Python application image.
# Stage 1 installs the API, FastHTML, and voice-runtime dependencies with uv.
FROM python:3.13-slim AS builder

WORKDIR /app

# Install git in builder stage (needed for any pip install from git URLs)
RUN apt-get update && apt-get install -y \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# uv (https://github.com/astral-sh/uv) for ~5-10x faster installs than pip.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Build the venv at the path it will live at in the final image, so shebangs
# and console-scripts inside the venv reference the correct runtime location
# after COPY --from.
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN python -m venv "$VIRTUAL_ENV"

# Layer 1: API deps. Cache invalidates only when requirements.txt changes.
RUN --mount=type=bind,source=api/requirements.txt,target=/tmp/req.txt \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r /tmp/req.txt

# Replace the desktop OpenCV wheel with its headless equivalent and cache the
# tokenizer needed by the voice pipeline. Pipecat itself is pinned in the
# requirements file to the upstream FastVoice-compatible revision.
#   1. Swap opencv-python (pulled by pipecat[webrtc]) for opencv-python-headless.
#      The non-headless build links against X11/Qt (libxcb*); without those
#      shared libs in the image, `import cv2` fails at runtime.
#   2. Pre-download NLTK's punkt_tab tokenizer so pipecat's text processing
#      doesn't hit the network on first agent run. NLTK auto-finds it under
#      sys.prefix/nltk_data, so it travels with the venv on COPY.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip uninstall opencv-python \
 && uv pip install opencv-python-headless \
 && python -c "import nltk; nltk.download('punkt_tab', download_dir='/opt/venv/nltk_data', quiet=True)"

# Strip caches, bundled tests/examples, stubs, and non-Python source artifacts
# from third-party distributions. The runtime image contains no Node toolchain.
RUN find /opt/venv -type f -name '*.pyc' -delete && \
    find /opt/venv -type d -name '__pycache__' -prune -exec rm -rf {} + && \
    find /opt/venv -type f -name '*.pyo' -delete && \
    find /opt/venv -type d \( -name tests -o -name test -o -name examples \) -prune -exec rm -rf {} + && \
    find /opt/venv -name '*.pyi' -delete && \
    find /opt/venv -type f \( -name '*.ts' -o -name '*.tsx' -o -name 'tsconfig*.json' \) -delete

# Stage 2: Static ffmpeg binary (avoids apt ffmpeg pulling mesa/libllvm for
# hardware acceleration we don't use server-side).
#
# Source: BtbN/FFmpeg-Builds, served from GitHub's release-assets CDN (fast,
# highly available, multi-arch). We pin a specific build for reproducibility,
# but to a *month-end* autobuild tag — not a daily one. BtbN prunes daily
# autobuilds after ~2 weeks (the previous pin was a daily tag and started
# 404ing once GC'd), but keeps one month-end snapshot per month long-term
# (~2 years back). A dated tag's assets are immutable, so the per-arch sha256
# below never rots: builds stay reproducible AND integrity-verified.
#
# To upgrade ffmpeg: bump BTBN_TAG + BTBN_REV to a newer month-end autobuild
# and refresh the two sha256s. No download needed — read tag, revision and
# per-asset sha256 straight from the GitHub release-asset metadata:
#   gh api repos/BtbN/FFmpeg-Builds/releases/tags/<tag> \
#     --jq '.assets[] | select(.name|test("(linux64|linuxarm64)-gpl\\.tar\\.xz$")) | "\(.name) \(.digest)"'
#
# `--speed-limit/--speed-time` aborts a *stalled* transfer after 30s of <1KB/s
# (the cause of "stuck" builds) without killing a slow-but-progressing
# download; `--max-time` is a hard backstop; `--retry` rides out transient CDN
# hiccups. The archive nests binaries under bin/, so locate them with `find`.
FROM debian:trixie-slim AS ffmpeg-static
ARG TARGETARCH
ARG BTBN_TAG=autobuild-2026-05-31-13-22
ARG BTBN_REV=N-124714-g49a77d37be
RUN set -eu ; \
    apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates xz-utils ; \
    rm -rf /var/lib/apt/lists/* ; \
    case "${TARGETARCH}" in \
      amd64) btbn_arch=linux64 ; \
             sha256=ee052121296e6479325e09c6097d48e72a4af472d18c2b94388b5405dcde6cce ;; \
      arm64) btbn_arch=linuxarm64 ; \
             sha256=e97545305043794cdf7b698d713e29291464e0c35bb8e0f3ff1f62e4c56eedd6 ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2 ; exit 1 ;; \
    esac ; \
    url="https://github.com/BtbN/FFmpeg-Builds/releases/download/${BTBN_TAG}/ffmpeg-${BTBN_REV}-${btbn_arch}-gpl.tar.xz" ; \
    mkdir -p /tmp/ffmpeg ; cd /tmp/ffmpeg ; \
    echo "Downloading ffmpeg (${BTBN_TAG}) from ${url}" ; \
    curl -fsSL --connect-timeout 20 --speed-limit 1024 --speed-time 30 \
         --max-time 600 --retry 3 --retry-delay 5 --retry-all-errors \
         -o ffmpeg.tar.xz "${url}" ; \
    echo "${sha256}  ffmpeg.tar.xz" | sha256sum -c - ; \
    tar -xJf ffmpeg.tar.xz ; \
    ffmpeg_bin="$(find /tmp/ffmpeg -type f -name ffmpeg | head -n1)" ; \
    ffprobe_bin="$(find /tmp/ffmpeg -type f -name ffprobe | head -n1)" ; \
    [ -n "${ffmpeg_bin}" ] && [ -n "${ffprobe_bin}" ] ; \
    mv "${ffmpeg_bin}" "${ffprobe_bin}" /usr/local/bin/ ; \
    chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe ; \
    rm -rf /tmp/ffmpeg

# Stage 3: Minimal runtime image.
FROM python:3.13-slim AS runner

WORKDIR /app

RUN groupadd --system fastvoice \
 && useradd --system --gid fastvoice --no-log-init --home-dir /app --shell /usr/sbin/nologin fastvoice \
 && chown fastvoice:fastvoice /app

# Static ffmpeg + ffprobe (used by audio_converter, audio_file_cache, etc.)
COPY --from=ffmpeg-static /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg-static /usr/local/bin/ffprobe /usr/local/bin/ffprobe

# Copy the populated venv from the builder stage. NLTK data lives at
# /opt/venv/nltk_data and is auto-discovered via sys.prefix.
COPY --from=builder /opt/venv /opt/venv

# Activate the venv for subsequent RUN/CMD layers.
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# Set Python to not generate .pyc files in runtime
ENV PYTHONDONTWRITEBYTECODE=1
# Unbuffered output for better container logging
ENV PYTHONUNBUFFERED=1

# Copy application code (chown at copy-time avoids a duplicate /app layer
# from a later `RUN chown -R`, which would double the on-disk size of /app).
COPY --chown=fastvoice:fastvoice ./api ./api
COPY --chown=fastvoice:fastvoice ./web ./web
COPY --chown=fastvoice:fastvoice ./static ./static

# Entrypoint scripts.
#   start_services_docker.sh — single-container (docker-compose) entrypoint
#     that runs every service in one process tree.
#   run_*.sh                 — per-service entrypoints used by the Helm chart,
#     which runs each workload (web, arq-worker, ari-manager,
#     campaign-orchestrator, migrate) as its own pod. Keep this list in sync
#     with the command:[] entries in deploy/helm/dograh/templates/*.yaml.
#   drain_web.sh             — web pod preStop hook (call-safe scale-down); see
#     lifecycle.preStop in deploy/helm/dograh/templates/web-deployment.yaml.
COPY --chown=fastvoice:fastvoice \
     ./scripts/start_services_docker.sh \
     ./scripts/run_migrate.sh \
     ./scripts/run_web.sh \
     ./scripts/run_arq_worker.sh \
     ./scripts/run_ari_manager.sh \
     ./scripts/run_campaign_orchestrator.sh \
     ./scripts/drain_web.sh \
     ./scripts/

# Product documentation is read at runtime by the MCP documentation tools.
COPY --chown=fastvoice:fastvoice ./docs ./docs

ENV PYTHONPATH=/app

# Disable file logging in Docker - logs go to stdout for docker logs
ENV LOG_TO_FILE=false

USER fastvoice

# Expose the port FastAPI will run on
EXPOSE 8000

# Run the FastAPI app with uvicorn
CMD ["./scripts/start_services_docker.sh"]
