"""End-to-end-bewijs: een echte HR-import via de API vult `analyze_skill_gap` (Fase 3 dag 4,
BE-AGT-061).

Dit is het exacte gat dat OP-26/deze sprint bestaat om te dichten: `analyze_skill_gap`
(`src/core/tool_broker/hr_registry.py`) bestaat al sinds 2026-08-15, maar had tot deze sprint
geen pad om data in `skills`/`role_required_skills`/`employee_skills` te krijgen en gaf dus
altijd een leeg resultaat. Dit bewijst het VOLLEDIGE pad: een echte POST naar de dag-3-
endpoints, gevolgd door een directe aanroep van de tool, tegen een echte Postgres-database.

**Waarom de rol vooraf gezaaid moet worden.** Het import-pad maakt bewust NOOIT automatisch een
`Role` aan (sprint-plan Ontwerpbeslissing 3) -- een rij die naar een onbestaande rol verwijst
wordt afgewezen, niet aangemaakt. Deze test zaait daarom vooraf een "Accountant"-rol en koppelt
de al-gezaaide tenant-1-gebruiker (`user@integration.test`, id 2) daaraan, zodat de
rol-vereiste-import ("Accountant heeft IFRS nodig") kan resolven.
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

_TENANT_ID = 1  # de conftest.py-gezaaide "Default Tenant"
_ACCOUNTANT_USER_EMAIL = "user@integration.test"  # conftest.py-gezaaid, id=2, tenant 1


@pytest_asyncio.fixture
async def accountant_role_seeded(postgres_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Zaait Role('Accountant', tenant 1) en koppelt de bestaande niet-admin-gebruiker erop."""
    with TenantFilterBypass():
        role = Role(name="Accountant", tenant_id=_TENANT_ID, is_active=True)
        postgres_session.add(role)
        await postgres_session.flush()

        user_id = (
            await postgres_session.execute(
                select(User.id).where(
                    User.email == _ACCOUNTANT_USER_EMAIL, User.tenant_id == _TENANT_ID
                )
            )
        ).scalar_one()

        await postgres_session.execute(insert(user_roles).values(user_id=user_id, role_id=role.id))
        await postgres_session.commit()
    yield


async def test_a_real_import_makes_analyze_skill_gap_return_a_non_empty_result(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    accountant_role_seeded: None,
    postgres_session: AsyncSession,
) -> None:
    skill_import = await client.post(
        "/api/v1/hr/skills/import",
        data={"entity_type": "skill"},
        files={"file": ("skills.csv", b"name,category\nIFRS,Finance\n", "text/csv")},
        headers=admin_auth_headers,
    )
    assert skill_import.status_code == 200, skill_import.json()
    assert skill_import.json()["data"]["inserted"] == 1

    requirement_import = await client.post(
        "/api/v1/hr/skills/import",
        data={"entity_type": "role_requirement"},
        files={
            "file": (
                "requirements.csv",
                b"role_name,skill_name,required_level\nAccountant,IFRS,3\n",
                "text/csv",
            )
        },
        headers=admin_auth_headers,
    )
    assert requirement_import.status_code == 200, requirement_import.json()
    assert requirement_import.json()["data"]["inserted"] == 1
    assert requirement_import.json()["data"]["errors"] == []

    assessment_import = await client.post(
        "/api/v1/hr/skills/import",
        data={"entity_type": "employee_assessment"},
        files={
            "file": (
                "assessments.csv",
                f"user_email,skill_name,level\n{_ACCOUNTANT_USER_EMAIL},IFRS,4\n".encode(),
                "text/csv",
            )
        },
        headers=admin_auth_headers,
    )
    assert assessment_import.status_code == 200, assessment_import.json()
    assert assessment_import.json()["data"]["inserted"] == 1
    assert assessment_import.json()["data"]["errors"] == []

    @asynccontextmanager
    async def _session_factory() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    registry = HRToolRegistry(session_factory=_session_factory)
    result = await registry.execute_hr_tool(GAP_TOOL_NAME, {}, tenant_id=_TENANT_ID)

    assert result["success"] is True
    assert result["gap_count"] > 0, "analyze_skill_gap gaf een leeg resultaat na een echte import"
    gaps_by_key = {(gap["role"], gap["skill"]): gap for gap in result["gaps"]}
    # dict-lookup i.p.v. next(...) -- een StopIteration is een onleesbare failure; dit geeft
    # een gewone AssertionError met de daadwerkelijke sleutels erbij (code-review dag 4).
    assert ("Accountant", "IFRS") in gaps_by_key, list(gaps_by_key)
    accountant_gap = gaps_by_key[("Accountant", "IFRS")]
    assert accountant_gap["required_level"] == 3
    assert accountant_gap["holders"] == 1
    assert accountant_gap["meeting_requirement"] == 1  # niveau 4 >= vereiste niveau 3
    assert accountant_gap["below_requirement"] == 0
    assert accountant_gap["unassessed"] == 0
