"""
Unit tests for ActivePiecesService tenant-binding correctness (Phase 3).

These tests enforce that:
- _get_project_for_tenant reads ONLY from local first-party bindings (fail-closed).
- _get_or_create_project_for_tenant never re-uses a remote project that belongs
  to a different tenant; it creates a NEW dedicated project.
- create_connection_for_tenant persists a local connection binding.
- execute_workflow resolves project_id from local binding, not from remote /projects.
- list_flows returns empty when no local project binding exists for the tenant.
"""

from types import SimpleNamespace
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.activepieces.service import ActivePiecesService
from src.core.activepieces.transformer import FlowTransformer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(
    *,
    flow_repo: Optional[object] = None,
    conn_repo: Optional[object] = None,
    client: Optional[object] = None,
    db: Optional[object] = None,
) -> ActivePiecesService:
    """Build an ActivePiecesService with controlled deps injected."""
    svc = ActivePiecesService(client=None, db=db)
    if client is not None:
        svc._client = client
    if flow_repo is not None:
        svc._flow_repo = flow_repo
    if conn_repo is not None:
        svc._conn_repo = conn_repo
    return svc


def _mock_client(*, project_list: Optional[list] = None) -> MagicMock:
    """Return a mock ActivePiecesClient."""
    client = MagicMock()
    client.is_available = MagicMock(return_value=True)
    if project_list is not None:
        client._make_request = AsyncMock(
            return_value={"data": project_list}
        )
    return client


def _flow_binding(tenant_id: int, project_id: str) -> SimpleNamespace:
    return SimpleNamespace(tenant_id=tenant_id, project_id=project_id)


def _conn_binding(tenant_id: int, project_id: str) -> SimpleNamespace:
    return SimpleNamespace(tenant_id=tenant_id, project_id=project_id)


# ---------------------------------------------------------------------------
# _get_project_for_tenant -- fail-closed behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_project_for_tenant_returns_none_when_no_local_binding() -> None:
    """Should return None (fail-closed) when no local flow or connection binding exists."""
    flow_repo = MagicMock()
    flow_repo.list_by_tenant = AsyncMock(return_value=[])
    conn_repo = MagicMock()
    conn_repo.list_by_tenant = AsyncMock(return_value=[])

    # Client must NOT be called at all
    client = MagicMock()
    client._make_request = AsyncMock()

    svc = _make_service(flow_repo=flow_repo, conn_repo=conn_repo, client=client)

    result = await svc._get_project_for_tenant(tenant_id=7)

    assert result is None
    # The remote /projects endpoint must never be consulted
    client._make_request.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_project_for_tenant_returns_project_id_from_local_flow_binding() -> None:
    """Should return the project_id stored in the first-party flow binding."""
    flow_repo = MagicMock()
    flow_repo.list_by_tenant = AsyncMock(
        return_value=[_flow_binding(tenant_id=3, project_id="proj-tenant-3")]
    )
    conn_repo = MagicMock()
    conn_repo.list_by_tenant = AsyncMock(return_value=[])

    client = MagicMock()
    client._make_request = AsyncMock()

    svc = _make_service(flow_repo=flow_repo, conn_repo=conn_repo, client=client)

    result = await svc._get_project_for_tenant(tenant_id=3)

    assert result == "proj-tenant-3"
    client._make_request.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_project_for_tenant_falls_back_to_connection_binding_when_no_flow() -> None:
    """Should consult conn_repo when flow_repo is empty."""
    flow_repo = MagicMock()
    flow_repo.list_by_tenant = AsyncMock(return_value=[])
    conn_repo = MagicMock()
    conn_repo.list_by_tenant = AsyncMock(
        return_value=[_conn_binding(tenant_id=5, project_id="proj-tenant-5")]
    )

    svc = _make_service(flow_repo=flow_repo, conn_repo=conn_repo)

    result = await svc._get_project_for_tenant(tenant_id=5)

    assert result == "proj-tenant-5"


# ---------------------------------------------------------------------------
# _get_or_create_project_for_tenant -- must NOT reuse another tenant's project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_or_create_returns_the_project_of_the_client_not_a_local_binding() -> None:
    """Het project is dat van de verbinding van de tenant, ook als een lokale rij iets anders zegt."""
    flow_repo = MagicMock()
    flow_repo.list_by_tenant = AsyncMock(
        return_value=[_flow_binding(tenant_id=1, project_id="proj-oud-lokaal")]
    )
    conn_repo = MagicMock()
    conn_repo.list_by_tenant = AsyncMock(return_value=[])

    client = MagicMock()
    client.eigen_project = MagicMock(return_value="proj-van-de-verbinding")
    client._make_request = AsyncMock()

    svc = _make_service(flow_repo=flow_repo, conn_repo=conn_repo, client=client)

    result = await svc._get_or_create_project_for_tenant(tenant_id=1)

    assert result == "proj-van-de-verbinding"
    client._make_request.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_or_create_never_creates_a_project_remotely() -> None:
    """
    SECURITY: de service maakt geen project aan (geen POST /projects) en kiest niet het eerste
    project van de server. Zonder verbinding is er geen project.
    """
    flow_repo = MagicMock()
    flow_repo.list_by_tenant = AsyncMock(return_value=[])
    conn_repo = MagicMock()
    conn_repo.list_by_tenant = AsyncMock(return_value=[])

    client = MagicMock()
    client.eigen_project = MagicMock(return_value="proj-van-de-verbinding")
    client._make_request = AsyncMock()

    svc = _make_service(flow_repo=flow_repo, conn_repo=conn_repo, client=client)

    await svc._get_or_create_project_for_tenant(tenant_id=2)

    client._make_request.assert_not_called()


# ---------------------------------------------------------------------------
# execute_workflow -- must not use a different tenant's project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execute_workflow_uses_tenant_bound_project_not_first_remote() -> None:
    """
    SECURITY: execute_workflow for tenant 2 must never reach tenant 1's project.
    The project_id must come from the local tenant binding.
    """
    flow_repo = MagicMock()
    # Tenant 2 has a binding to proj-for-tenant-2
    flow_repo.list_by_tenant = AsyncMock(
        return_value=[_flow_binding(tenant_id=2, project_id="proj-for-tenant-2")]
    )
    flow_repo.create = AsyncMock(return_value=MagicMock())
    conn_repo = MagicMock()
    conn_repo.list_by_tenant = AsyncMock(return_value=[])

    client = MagicMock()
    client.eigen_project = MagicMock(return_value="proj-for-tenant-2")
    client.is_available = MagicMock(return_value=True)
    # De client bouwt de flow met de versies van zijn eigen server; hier legacy-vorm.
    client.build_flow_definition = AsyncMock(side_effect=FlowTransformer.react_flow_to_activepieces)
    # list_project_flows returns nothing so a new flow will be created
    client.list_project_flows = AsyncMock(return_value=[])
    client.create_flow = AsyncMock(return_value={"id": "flow-new", "status": "DISABLED"})
    client.trigger_flow = AsyncMock(
        return_value={"execution_id": "run-1", "status": "RUNNING"}
    )

    db = AsyncMock()
    svc = _make_service(flow_repo=flow_repo, conn_repo=conn_repo, client=client, db=db)

    workflow_definition = {"nodes": [], "edges": []}
    result = await svc.execute_workflow(
        workflow_definition=workflow_definition,
        tenant_id=2,
    )

    assert result["success"] is True
    # create_flow must be called with tenant 2's project, never with a foreign project
    client.create_flow.assert_awaited_once()
    actual_project_id = client.create_flow.await_args[0][0]
    assert actual_project_id == "proj-for-tenant-2"


@pytest.mark.asyncio
async def test_execute_workflow_builds_the_flow_through_the_client() -> None:
    """De flow moet via de client gebouwd worden: alleen die kent de serverversie
    (pinning sinds AP 0.82, ['output'] sinds 0.85.4). Mutatie: terug naar
    FlowTransformer.react_flow_to_activepieces in execute_workflow -> rood."""
    flow_repo = MagicMock()
    flow_repo.list_by_tenant = AsyncMock(
        return_value=[_flow_binding(tenant_id=2, project_id="proj-for-tenant-2")]
    )
    flow_repo.create = AsyncMock(return_value=MagicMock())
    conn_repo = MagicMock()
    conn_repo.list_by_tenant = AsyncMock(return_value=[])
    client = MagicMock()
    client.eigen_project = MagicMock(return_value="proj-for-tenant-2")
    client.is_available = MagicMock(return_value=True)
    built = {"displayName": "Gebouwd door client", "trigger": {}, "actions": {}}
    client.build_flow_definition = AsyncMock(return_value=built)
    client.list_project_flows = AsyncMock(return_value=[])
    client.create_flow = AsyncMock(return_value={"id": "flow-new", "status": "DISABLED"})
    client.trigger_flow = AsyncMock(return_value={"execution_id": "run-1", "status": "RUNNING"})
    svc = _make_service(flow_repo=flow_repo, conn_repo=conn_repo, client=client, db=AsyncMock())

    await svc.execute_workflow(workflow_definition={"name": "x", "nodes": [], "edges": []}, tenant_id=2)

    assert client.create_flow.await_args[0][1] is built


# ---------------------------------------------------------------------------
# create_connection_for_tenant -- must persist local binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_connection_for_tenant_persists_local_binding() -> None:
    """After creating a remote connection, a local binding must be stored in conn_repo."""
    flow_repo = MagicMock()
    flow_repo.list_by_tenant = AsyncMock(
        return_value=[_flow_binding(tenant_id=4, project_id="proj-4")]
    )
    conn_repo = MagicMock()
    conn_repo.list_by_tenant = AsyncMock(return_value=[])
    conn_repo.create = AsyncMock(return_value=MagicMock())

    client = MagicMock()
    client.eigen_project = MagicMock(return_value="proj-4")
    # POST /app-connections response (de vorm die AP 0.92.1 geeft, gemeten 2026-10-25)
    client._make_request = AsyncMock(
        return_value={
            "id": "ap-conn-999",
            "displayName": "slack_4",
            "pieceName": "@activepieces/piece-slack",
            "projectIds": ["proj-4"],
            "created": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
        }
    )

    db = AsyncMock()
    svc = _make_service(flow_repo=flow_repo, conn_repo=conn_repo, client=client, db=db)

    await svc.create_connection_for_tenant(
        tenant_id=4,
        app_name="slack",
        config={"type": "SECRET_TEXT", "secret_text": "geheim-voor-de-test"},
    )

    # Must call conn_repo.create with the correct tenant_id and ap_connection_id
    conn_repo.create.assert_awaited_once()
    call_kwargs = conn_repo.create.await_args[1]
    assert call_kwargs["tenant_id"] == 4
    assert call_kwargs["ap_connection_id"] == "ap-conn-999"
    assert call_kwargs["project_id"] == "proj-4"
    # db.commit must be called to persist
    db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# get_tenant_flows -- must return empty when no local project binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_tenant_flows_lists_the_project_of_the_client_not_a_local_binding() -> None:
    """
    De flows van een tenant zijn die in het project van zijn verbinding (`eigen_project`); er is
    geen lokale rij nodig en er wordt geen project gezocht of aangemaakt.
    """
    flow_repo = MagicMock()
    flow_repo.list_by_tenant = AsyncMock(return_value=[])
    conn_repo = MagicMock()
    conn_repo.list_by_tenant = AsyncMock(return_value=[])

    client = MagicMock()
    client.eigen_project = MagicMock(return_value="proj-van-de-verbinding")
    client._make_request = AsyncMock()
    client.list_project_flows = AsyncMock(return_value=[])

    svc = _make_service(flow_repo=flow_repo, conn_repo=conn_repo, client=client)

    result = await svc.get_tenant_flows(tenant_id=99)

    assert result == []
    client.list_project_flows.assert_awaited_once_with("proj-van-de-verbinding")
    client._make_request.assert_not_called()
