"""Replay-safe FastSME suite-ticket verification for FastOffice SSO."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import redis.asyncio as aioredis

from api.constants import REDIS_URL


def enabled() -> bool:
    return bool(os.getenv("FASTOFFICE_SSO_SECRET", "").strip())


def _allowed_email(email: str) -> bool:
    normalized = email.strip().lower()
    emails = {
        value.strip().lower()
        for value in os.getenv("GOOGLE_ALLOWED_EMAILS", "").split(",")
        if value.strip()
    }
    domains = {
        value.strip().lower()
        for value in os.getenv("GOOGLE_ALLOWED_DOMAINS", "").split(",")
        if value.strip()
    }
    if emails and normalized not in emails:
        return False
    if domains and normalized.rsplit("@", 1)[-1] not in domains:
        return False
    return bool(normalized and "@" in normalized)


def _verify_signature(token: str, *, audience: str) -> dict[str, Any] | None:
    secret = os.getenv("FASTOFFICE_SSO_SECRET", "").strip()
    if not secret:
        return None
    try:
        encoded, supplied = token.split(".", 1)
        expected = hmac.new(
            secret.encode(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        )
        now = int(time.time())
        required = {
            "sub",
            "email",
            "name",
            "org_id",
            "org_name",
            "role",
            "jti",
            "exp",
            "aud",
        }
        if not required.issubset(payload):
            return None
        if payload.get("aud") != audience or int(payload.get("exp", 0)) < now:
            return None
        if not _allowed_email(str(payload.get("email", ""))):
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


async def redeem_suite_ticket(
    token: str,
    *,
    audience: str = "voice",
    replay_store=None,
) -> dict[str, Any] | None:
    """Verify and consume one short-lived, audience-bound FastOffice ticket."""
    payload = _verify_signature(token, audience=audience)
    if payload is None:
        return None

    now = int(time.time())
    expires_in = max(1, int(payload["exp"]) - now)
    digest = hashlib.sha256(str(payload["jti"]).encode()).hexdigest()
    key = f"fastvoice:suite-ticket:{digest}"
    client = replay_store or aioredis.from_url(REDIS_URL, decode_responses=True)
    owns_client = replay_store is None
    try:
        consumed = await client.set(key, "1", ex=expires_in, nx=True)
        return payload if consumed else None
    except Exception:  # noqa: BLE001 - replay-store failures must fail closed.
        return None
    finally:
        if owns_client:
            await client.aclose()
