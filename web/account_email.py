"""Transactional account-email delivery through Postmark."""

from __future__ import annotations

import html
import os

import httpx


async def send_account_link(email: str, purpose: str, token: str) -> bool:
    api_token = os.getenv("POSTMARK_API_TOKEN", "").strip()
    sender = os.getenv("FROM_EMAIL", "info@fastsme.com").strip()
    public_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    if not api_token or not sender or purpose not in {"verify", "reset"}:
        return False

    if purpose == "verify":
        subject = "Verify your FastVoice account"
        path = f"/auth/verify/{token}"
        action = "Verify account"
    else:
        subject = "Reset your FastVoice password"
        path = f"/auth/reset/{token}"
        action = "Reset password"
    link = html.escape(f"{public_url}{path}", quote=True)
    body = (
        "<p>Hello,</p>"
        f'<p><a href="{link}">{html.escape(action)}</a></p>'
        "<p>This single-use link expires automatically.</p>"
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": api_token},
                json={
                    "From": sender,
                    "To": email,
                    "Subject": subject,
                    "HtmlBody": body,
                    "MessageStream": "outbound",
                },
            )
        return response.is_success
    except httpx.HTTPError:
        return False
