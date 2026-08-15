from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db.organization_configuration_client import LEASE_COMPLETED, LEASE_PENDING
from api.services import organization_bootstrap as bootstrap

ORG_ID = 42
LEASE_OWNER_TOKEN = "lease-owner-token"


@pytest.fixture
def state(monkeypatch):
    value = SimpleNamespace(row=None)
    calls = SimpleNamespace(
        get=AsyncMock(side_effect=lambda *_: value.row),
        claim=AsyncMock(return_value=LEASE_OWNER_TOKEN),
        complete=AsyncMock(),
    )
    monkeypatch.setattr(bootstrap.db_client, "get_configuration", calls.get)
    monkeypatch.setattr(bootstrap.db_client, "claim_configuration_lease", calls.claim)
    monkeypatch.setattr(bootstrap.db_client, "complete_configuration_lease", calls.complete)
    return value, calls


@pytest.mark.asyncio
async def test_completed_local_bootstrap_short_circuits(state):
    value, calls = state
    value.row = SimpleNamespace(value={"status": LEASE_COMPLETED})

    assert await bootstrap.ensure_organization_bootstrapped(ORG_ID, created_by="user")
    calls.claim.assert_not_awaited()
    calls.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_or_pending_org_is_completed_locally(state):
    value, calls = state
    value.row = SimpleNamespace(value={"status": LEASE_PENDING})

    assert await bootstrap.ensure_organization_bootstrapped(ORG_ID, created_by="user")
    calls.claim.assert_awaited_once()
    calls.complete.assert_awaited_once_with(
        ORG_ID, bootstrap._BOOTSTRAP_KEY, LEASE_OWNER_TOKEN
    )


@pytest.mark.asyncio
async def test_concurrent_bootstrap_does_not_duplicate_work(state):
    _, calls = state
    calls.claim.return_value = None

    assert not await bootstrap.ensure_organization_bootstrapped(
        ORG_ID, created_by="user"
    )
    calls.complete.assert_not_awaited()
