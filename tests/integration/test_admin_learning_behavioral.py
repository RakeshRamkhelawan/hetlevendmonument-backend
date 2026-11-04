"""
Admin Learning — User behavioral journeys (ADR-026).

Tests valideren wat een platform-admin ZIET en ERVAART bij het beheren van
tenant LLM budgetten. Deze tests draaien tegen de volledige stack
(FastAPI + echte PostgreSQL + echte dependency chain).

Run:
    make test-db-up
    pytest tests/integration/test_admin_learning_behavioral.py -v
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from src.core.auth.jwt_handler import jwt_handler


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_views_and_updates_tenant_llm_budget(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    test_tenant_id: int,
) -> None:
    """
    Verhaal: Priya is platform-admin en wil het LLM-budget van haar tenant
    inzien en aanpassen voordat het team gaat experimenteren met nieuwe
    AI-workflows.

    Zij verwacht:
      1. Bij eerste bezoek ziet ze een default budget (soft=10 EUR, hard=50 EUR).
      2. Zij kan het hard-cap verhogen naar 100 EUR.
      3. Na wijzigen ziet ze direct het nieuwe bedrag terug.
      4. De 'remaining' waarden kloppen met het nieuwe budget.
    """
    tenant_id = test_tenant_id
    base_path = f"/admin/learning/tenants/{tenant_id}/llm-budget"

    # ── Act 1: Priya opent het budget-dashboard voor de eerste keer ──────────
    get_response = await client.get(base_path, headers=admin_auth_headers)

    # ── Assert 1: ze ziet een leesbaar budgetoverzicht ───────────────────────
    assert get_response.status_code == 200, get_response.text
    budget = get_response.json()
    assert budget["tenant_id"] == tenant_id
    assert budget["budget_eur_soft"] == 10.0, "Default soft cap moet 10 EUR zijn"
    assert budget["budget_eur_hard"] == 50.0, "Default hard cap moet 50 EUR zijn"
    assert budget["spent_eur"] == 0.0
    assert budget["remaining_soft"] == 10.0
    assert budget["remaining_hard"] == 50.0

    # ── Act 2: Priya verhoogt het hard-cap naar 100 EUR ──────────────────────
    put_response = await client.put(
        base_path,
        headers=admin_auth_headers,
        json={"budget_eur_soft": 25.0, "budget_eur_hard": 100.0},
    )

    # ── Assert 2: de wijziging wordt direct geaccepteerd ─────────────────────
    assert put_response.status_code == 200, put_response.text
    updated = put_response.json()
    assert updated["budget_eur_soft"] == 25.0
    assert updated["budget_eur_hard"] == 100.0
    assert updated["remaining_soft"] == 25.0
    assert updated["remaining_hard"] == 100.0

    # ── Act 3: Priya vernieuwt het dashboard ─────────────────────────────────
    get_after = await client.get(base_path, headers=admin_auth_headers)

    # ── Assert 3: het nieuwe budget is persistent en direct zichtbaar ────────
    assert get_after.status_code == 200
    refreshed = get_after.json()
    assert refreshed["budget_eur_hard"] == 100.0
    assert refreshed["month"] == updated["month"], "Zelfde maand als de update"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_cannot_view_other_tenant_budget(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
) -> None:
    """
    Verhaal: Priya probeert per ongeluk het budget van een andere tenant
    te bekijken (tenant_id=99999). Het systeem moet dit expliciet weigeren
    zodat ze niet per ongeluk vertrouwelijke data van een andere klant ziet.

    Zij verwacht: een duidelijke 403 met een begrijpelijke foutmelding.
    """
    foreign_tenant_path = "/admin/learning/tenants/99999/llm-budget"

    get_response = await client.get(foreign_tenant_path, headers=admin_auth_headers)

    # ── Assert: expliciete toegangsweigering ─────────────────────────────────
    assert get_response.status_code == 403, (
        f"Cross-tenant budget-lezing moet 403 geven, kreeg {get_response.status_code}"
    )
    body = get_response.json()
    assert "detail" in body
    assert "own tenant" in body["detail"].lower() or "forbidden" in body["detail"].lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_system_admin_can_access_any_tenant_budget(
    client: AsyncClient,
    db_session: Any,
    test_tenant_id: int,
) -> None:
    """
    Verhaal: Alex is system_admin en moet alle tenant-budgetten kunnen
    inzien voor platform governance. Zijn system_admin rol geeft hem
    platform-wide toegang.
    """
    # ── Arrange: create a system_admin user in the database ──────────────────
    # Find the system_admin role id
    role_result = await db_session.execute(
        text("SELECT id FROM roles WHERE name = 'system_admin' AND tenant_id = 1")
    )
    system_admin_role_id = role_result.scalar()

    if system_admin_role_id is None:
        pytest.skip("system_admin role not seeded in test database")

    # Create a dedicated system admin user
    await db_session.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, is_active, is_superuser, tenant_id) "
            "VALUES (9991, 'sysadmin@integration.test', '$2b$12$dummyhashfortests', true, true, 1) "
            "ON CONFLICT (id) DO NOTHING"
        )
    )
    await db_session.execute(
        text(
            "INSERT INTO user_roles (user_id, role_id) VALUES (9991, :role_id) ON CONFLICT DO NOTHING"
        ),
        {"role_id": system_admin_role_id},
    )
    await db_session.commit()

    # Build a JWT for this system admin
    token = jwt_handler.create_access_token(
        data={
            "sub": "9991",
            "user_id": 9991,
            "email": "sysadmin@integration.test",
            "tenant_id": 1,
        }
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Alex accesses a DIFFERENT tenant than his own
    foreign_path = f"/admin/learning/tenants/{test_tenant_id}/llm-budget"
    response = await client.get(foreign_path, headers=headers)

    # ── Assert: system_admin may view any tenant ─────────────────────────────
    assert response.status_code == 200, (
        f"System_admin moet elke tenant kunnen zien, kreeg {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body["tenant_id"] == test_tenant_id
