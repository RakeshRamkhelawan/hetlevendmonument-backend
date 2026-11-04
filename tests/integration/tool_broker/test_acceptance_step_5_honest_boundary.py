"""Integratietests voor HR Acceptatieketen Stap 5: Eerlijke HTTP-Boundary Validatie (SP-GENUINE-001 Dag 5).

Verifieert:
1. Stap 5 is fail-closed (ROOD): zonder data levert analyze_skill_gap nul rijen op,
   waardoor acceptance_thread.py stap 5 faalt zoals ontworpen.
2. Proefdata wordt uitsluitend geladen via het officiele HTTP-endpoint POST /api/v1/hr/skills/import.
3. Na de echte HTTP CSV import wordt de keten GROEN: analyze_skill_gap retourneert echte
   kloofrijen uit de database zonder enige interne test-mock of direct database SQL manipulatie.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.models.rbac_models import Role, User, user_roles
from src.core.tool_broker.hr_registry import GAP_TOOL_NAME, HRToolRegistry

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_TENANT_ID = 1
_TEST_USER_EMAIL = "user@integration.test"


@pytest_asyncio.fixture
async def developer_role_seeded(postgres_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Zaait Role('Developer', tenant 1) en koppelt de bestaande test-gebruiker erop.

    De import-route weigert conform het ontwerp (ADR-036) om stil rollen aan te maken
    als ze niet bestaan. De rol moet geautoriseerd en aanwezig zijn in RBAC.
    """
    with TenantFilterBypass():
        role = Role(name="Developer", tenant_id=_TENANT_ID, is_active=True)
        postgres_session.add(role)
        await postgres_session.flush()

        user_id = (
            await postgres_session.execute(
                select(User.id).where(
                    User.email == _TEST_USER_EMAIL, User.tenant_id == _TENANT_ID
                )
            )
        ).scalar_one()

        await postgres_session.execute(insert(user_roles).values(user_id=user_id, role_id=role.id))
        await postgres_session.commit()
    yield


async def test_step_5_is_fail_closed_red_without_http_import(
    postgres_session: AsyncSession,
) -> None:
    """Stap 5 faalt wanneer er geen proefdata is geladen (fail-closed contract van acceptance_thread.py)."""
    @asynccontextmanager
    async def _session_factory() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    registry = HRToolRegistry(session_factory=_session_factory)
    result = await registry.execute_hr_tool(GAP_TOOL_NAME, {}, tenant_id=_TENANT_ID)

    assert result["success"] is True
    # Zonder proefdata MOET de klooflijst leeg zijn. Dit triggert in acceptance_thread.py:
    # 'de tool werkt maar geeft nul rijen -- de database bevat geen proefdata'
    assert result.get("gap_count", 0) == 0
    assert result.get("gaps", []) == []


async def test_step_5_becomes_green_exclusively_after_real_http_import(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    developer_role_seeded: None,
    postgres_session: AsyncSession,
) -> None:
    """Stap 5 wordt groen uitsluitend na een succesvolle import via het officiele HTTP POST endpoint."""
    @asynccontextmanager
    async def _session_factory() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    registry = HRToolRegistry(session_factory=_session_factory)

    # 1. Verifieer eerst dat stap 5 initieel 0 resultaten oplevert voor de Developer rol
    initial_result = await registry.execute_hr_tool(GAP_TOOL_NAME, {}, tenant_id=_TENANT_ID)
    developer_gaps = [
        gap for gap in initial_result.get("gaps", []) if gap.get("role") == "Developer"
    ]
    assert len(developer_gaps) == 0

    # 2. Laad proefdata uitsluitend via de officiele HTTP boundary POST /api/v1/hr/skills/import
    # Stap 2a: Skill importeren
    resp_skill = await client.post(
        "/api/v1/hr/skills/import",
        data={"entity_type": "skill"},
        files={"file": ("skills.csv", b"name,category\nPython,Engineering\n", "text/csv")},
        headers=admin_auth_headers,
    )
    assert resp_skill.status_code == 200, resp_skill.json()
    assert resp_skill.json()["data"]["inserted"] == 1

    # Stap 2b: Role requirement importeren
    resp_req = await client.post(
        "/api/v1/hr/skills/import",
        data={"entity_type": "role_requirement"},
        files={
            "file": (
                "requirements.csv",
                b"role_name,skill_name,required_level\nDeveloper,Python,3\n",
                "text/csv",
            )
        },
        headers=admin_auth_headers,
    )
    assert resp_req.status_code == 200, resp_req.json()
    assert resp_req.json()["data"]["inserted"] == 1

    # Stap 2c: Employee assessment importeren
    resp_assess = await client.post(
        "/api/v1/hr/skills/import",
        data={"entity_type": "employee_assessment"},
        files={
            "file": (
                "assessments.csv",
                f"user_email,skill_name,level\n{_TEST_USER_EMAIL},Python,2\n".encode(),
                "text/csv",
            )
        },
        headers=admin_auth_headers,
    )
    assert resp_assess.status_code == 200, resp_assess.json()
    assert resp_assess.json()["data"]["inserted"] == 1

    # 3. Voer analyze_skill_gap direct uit na de import
    result = await registry.execute_hr_tool(GAP_TOOL_NAME, {}, tenant_id=_TENANT_ID)

    assert result["success"] is True
    assert result["gap_count"] > 0

    # Zoek de zojuist via HTTP geimporteerde kloof
    gaps_by_key = {(gap["role"], gap["skill"]): gap for gap in result["gaps"]}
    assert ("Developer", "Python") in gaps_by_key

    dev_gap = gaps_by_key[("Developer", "Python")]
    assert dev_gap["required_level"] == 3
    assert dev_gap["holders"] == 1
    assert dev_gap["meeting_requirement"] == 0  # niveau 2 < vereiste 3
    assert dev_gap["below_requirement"] == 1
    assert dev_gap["unassessed"] == 0
