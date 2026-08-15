"""Idempotent, local-only organization bootstrap for FastVoice.

FastVoice is a BYOK application.  Creating or signing into an organization must
never mint a key, provision telephony, create a billing account, or call a
Dograh-hosted service.  Provider configuration is deliberately left empty so
the owner can add their own credentials from the Models and Telephony screens.
"""
from __future__ import annotations

from datetime import timedelta

from api.db import db_client
from api.db.organization_configuration_client import LEASE_COMPLETED
from api.enums import OrganizationConfigurationKey

BOOTSTRAP_LEASE_STALE_AFTER = timedelta(minutes=5)
_BOOTSTRAP_KEY = OrganizationConfigurationKey.ORGANIZATION_BOOTSTRAP.value


async def ensure_organization_bootstrapped(
    organization_id: int,
    *,
    created_by: str,
) -> bool:
    """Mark local organization setup complete without external side effects."""
    del created_by
    row = await db_client.get_configuration(organization_id, _BOOTSTRAP_KEY)
    if row and (row.value or {}).get("status") == LEASE_COMPLETED:
        return True

    owner_token = await db_client.claim_configuration_lease(
        organization_id,
        _BOOTSTRAP_KEY,
        BOOTSTRAP_LEASE_STALE_AFTER,
    )
    if owner_token is None:
        return False
    await db_client.complete_configuration_lease(
        organization_id,
        _BOOTSTRAP_KEY,
        owner_token,
    )
    return True
