"""De tweede HR-tool: `analyze_skill_gap` (ADR-036 OP-26).

`query_hr_database` telde koppen per functie. Daarmee kon de piloot zeggen hoeveel mensen een
rol bekleden, niet wat ze missen -- er waren geen vaardigheden, geen functie-eisen en geen
beoordelingen in het platform. Die drie tabellen zijn er nu (`20260815_hr_skills_tables`), en
deze tool maakt er de aftreksom van.

**Wat de tool bewust NIET doet.** Hij geeft geen personen terug, alleen tellingen per
(functie, vaardigheid). Alles wat een tool retourneert gaat de event bus op en wordt door het
leersubsysteem gepersisteerd; rij-data zou daarmee beoordelingen van individuele medewerkers
in een leeropslag zetten. Dat is dezelfde afweging als bij `query_hr_database` (OP-27), en hier
zwaarder: een oordeel over iemands vaardigheid is gevoeliger dan het feit dat hij een rol heeft.

**Drie categorieen die elkaar uitsluiten.** `meeting_requirement` + `below_requirement` +
`unassessed` telt op tot `holders`. Wie nooit beoordeeld is telt NIET als "haalt het niet":
niet gemeten is iets anders dan niet kunnen. Een eerdere versie van deze berekening gooide die
twee op een hoop -- de toelichting zei het goede, de aftreksom deed het andere.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# BEWUST op moduleniveau en niet in de helper. De `db_session`-fixture maakt per test een
# verse in-memory database met `Base.metadata.create_all`, en die ziet alleen de modellen die
# op dat moment geimporteerd zijn. Stond deze import in `_seed_gap`, dan gebeurde hij pas NA
# het aanmaken van het schema en faalde uitsluitend de EERSTE test in het bestand met
# "no such table: skills" -- daarna was de module geladen en slaagden de rest. Precies het
# soort volgorde-afhankelijkheid dat in CI willekeurig omvalt. (Gemeten 2026-08-15.)
from src.core.models.hr_skills_models import (  # noqa: E402
    EmployeeSkill,
    RoleRequiredSkill,
    Skill,
)

TOOL = "analyze_skill_gap"


@pytest.fixture(autouse=True)
def _allow_all_tools() -> Iterator[None]:
    """De permissielaag is hier niet het onderwerp; die heeft eigen tests."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


def _registry() -> Any:
    from src.core.tool_broker.hr_registry import HRToolRegistry

    return HRToolRegistry()


async def _seed_gap(
    session: AsyncSession,
    tenant_id: int,
    slug: str,
    role_name: str,
    skill_name: str,
    required_level: int,
    levels: list[int | None],
) -> None:
    """Een tenant met een functie die een vaardigheid eist en N bezetters.

    `levels` bepaalt per bezetter het beoordeelde niveau; `None` betekent niet beoordeeld.
    """
    from src.core.models.rbac_models import Role, Tenant, User

    session.add(Tenant(id=tenant_id, name=f"Tenant {slug}", slug=slug))
    await session.flush()

    role = Role(tenant_id=tenant_id, name=role_name)
    skill = Skill(tenant_id=tenant_id, name=skill_name)
    session.add_all([role, skill])
    await session.flush()

    session.add(
        RoleRequiredSkill(
            tenant_id=tenant_id,
            role_id=role.id,
            skill_id=skill.id,
            required_level=required_level,
        )
    )

    for index, level in enumerate(levels):
        member = User(
            tenant_id=tenant_id,
            email=f"{slug}-{index}@example.test",
            hashed_password="x",
            is_active=True,
        )
        member.roles.append(role)
        session.add(member)
        await session.flush()
        if level is not None:
            session.add(
                EmployeeSkill(
                    tenant_id=tenant_id,
                    user_id=member.id,
                    skill_id=skill.id,
                    level=level,
                )
            )
    await session.commit()


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheGapItself:
    async def test_three_categories_add_up_to_the_number_of_holders(
        self, db_session: AsyncSession
    ) -> None:
        """Haalt het, haalt het niet, en nooit beoordeeld -- samen de hele bezetting."""
        await _seed_gap(db_session, 1, "alpha", "Finance Analyst", "IFRS", 3, [4, 2, None])

        result = await _registry().execute_hr_tool(TOOL, {}, tenant_id=1)

        assert result["success"] is True
        row = result["gaps"][0]
        assert row["role"] == "Finance Analyst"
        assert row["skill"] == "IFRS"
        assert row["required_level"] == 3
        assert row["holders"] == 3
        assert row["meeting_requirement"] == 1, "niveau 4 haalt de eis van 3"
        assert row["below_requirement"] == 1, "niveau 2 haalt hem niet"
        assert row["unassessed"] == 1, "de derde is nooit beoordeeld"
        assert (
            row["meeting_requirement"] + row["below_requirement"] + row["unassessed"]
            == row["holders"]
        ), (
            "De drie categorieen moeten optellen tot de bezetting. Tellen ze niet op, dan "
            "verdwijnt of dubbeltelt er iemand en klopt het advies van de skill niet."
        )

    async def test_unassessed_is_not_counted_as_failing(self, db_session: AsyncSession) -> None:
        """Niemand beoordeeld betekent niet dat iedereen zakt.

        Dit is de regressie die de eerste versie van de berekening had: `holders - meeting`
        telde de niet-beoordeelden mee als "haalt het niet", terwijl de toelichting het
        tegenovergestelde beweerde.
        """
        await _seed_gap(db_session, 1, "alpha", "Engineer", "Python", 4, [None, None])

        result = await _registry().execute_hr_tool(TOOL, {}, tenant_id=1)

        row = result["gaps"][0]
        assert row["below_requirement"] == 0
        assert row["unassessed"] == 2

    async def test_a_role_without_holders_still_reports_its_gap(
        self, db_session: AsyncSession
    ) -> None:
        """Een onbezette functie is een kloof, geen ontbrekende regel.

        Zonder buitenwaartse join zou de rij helemaal uit het antwoord vallen en zou de skill
        concluderen dat er voor die functie niets te doen is -- terwijl de hele bezetting
        ontbreekt.
        """
        await _seed_gap(db_session, 1, "alpha", "Data Steward", "SQL", 3, [])

        result = await _registry().execute_hr_tool(TOOL, {}, tenant_id=1)

        assert result["gap_count"] == 1
        row = result["gaps"][0]
        assert row["role"] == "Data Steward"
        assert row["holders"] == 0
        assert row["meeting_requirement"] == 0

    async def test_role_filter_narrows_the_answer(self, db_session: AsyncSession) -> None:
        await _seed_gap(db_session, 1, "alpha", "Engineer", "Python", 3, [5])
        from src.core.models.rbac_models import Role

        role = Role(tenant_id=1, name="Recruiter")
        skill = Skill(tenant_id=1, name="Interviewing")
        db_session.add_all([role, skill])
        await db_session.flush()
        db_session.add(
            RoleRequiredSkill(tenant_id=1, role_id=role.id, skill_id=skill.id, required_level=2)
        )
        await db_session.commit()

        result = await _registry().execute_hr_tool(TOOL, {"role": "Recruiter"}, tenant_id=1)

        assert [row["role"] for row in result["gaps"]] == ["Recruiter"]


@pytest.mark.unit
@pytest.mark.asyncio
class TestTenantIsolation:
    async def test_the_gap_never_includes_another_tenant(self, db_session: AsyncSession) -> None:
        """Tenant A ziet geen vaardigheid, eis of beoordeling van tenant B.

        Verplicht per backend-patterns par. 11, en hier scherper dan bij een telling: een
        beoordeling die overwaait is een persoonsgegeven van een andere klant.
        """
        await _seed_gap(db_session, 1, "alpha", "Finance Analyst", "IFRS", 3, [4])
        await _seed_gap(db_session, 2, "beta", "Finance Analyst", "IFRS", 3, [1, 1, 1])

        result = await _registry().execute_hr_tool(TOOL, {}, tenant_id=1)

        assert result["gap_count"] == 1
        row = result["gaps"][0]
        assert row["holders"] == 1, (
            "De bezetting bevat gebruikers van een andere tenant. Dat is een datalek over "
            "tenantgrenzen heen, niet alleen een verkeerd getal."
        )
        assert row["meeting_requirement"] == 1
        assert row["below_requirement"] == 0

    async def test_model_cannot_choose_the_tenant_via_the_payload(
        self, db_session: AsyncSession
    ) -> None:
        """De tenant komt uit de executiecontext, nooit uit de door het model geschreven payload."""
        await _seed_gap(db_session, 1, "alpha", "Engineer", "Python", 3, [5])
        await _seed_gap(db_session, 2, "beta", "Engineer", "Python", 3, [1, 1])

        result = await _registry().execute_hr_tool(TOOL, {"tenant_id": 2}, tenant_id=1)

        assert result["gaps"][0]["holders"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestErasedUsersAreNotCounted:
    async def test_soft_deleted_user_drops_out_of_the_gap(self, db_session: AsyncSession) -> None:
        """Wie op grond van AVG art. 17 is gewist, houdt geen kloof open.

        De opzoeking hieronder zet EXPLICIET de tenantcontext en filtert zelf op tenant.
        Zonder dat slaagt deze test alleen zolang de ADR-004-listener toevallig niet
        geregistreerd is: `init_tenant_auto_filtering()` hangt een globale
        `do_orm_execute`-hook aan de Session-klasse die fail-secure is, dus zonder tenant in
        de ContextVar komen er NUL rijen terug. Lokaal met `-n 4` viel dat niet op, in de
        sequentiele CI-run wel -- daar had een eerdere test de listener al geregistreerd.
        Dat is exact ADR-036 OP-20, en de les daar is dat een test die alleen slaagt zonder
        die listener een configuratie test die in productie nooit voorkomt.
        """
        from sqlalchemy import select

        from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id
        from src.core.models.rbac_models import User

        await _seed_gap(db_session, 1, "alpha", "Engineer", "Python", 4, [2, 2])

        vorige_tenant = get_tenant_id()
        set_tenant_id(1)
        try:
            first = (
                await db_session.execute(
                    select(User).where(User.tenant_id == 1).order_by(User.id)
                )
            ).scalars().first()
        finally:
            set_tenant_id(vorige_tenant)

        assert first is not None, (
            "Geen gebruiker gevonden om te wissen. Draait de ADR-004-tenantfilter mee zonder "
            "dat deze test een tenant in de ContextVar zet? Zie ADR-036 OP-20."
        )
        first.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()

        result = await _registry().execute_hr_tool(TOOL, {}, tenant_id=1)

        assert result["gaps"][0]["holders"] == 1


@pytest.mark.unit
class TestTheQueryItself:
    def test_every_table_carries_its_own_tenant_predicate(self) -> None:
        """De tenantgrens staat op ELKE tabel, niet alleen in de WHERE.

        `user_roles` heeft geen tenantkolom. Zonder een eigen predicaat op `users`,
        `role_required_skills`, `skills` en `employee_skills` zou een vervuilde associatierij
        gegevens van een andere tenant binnenhalen. De ADR-004-hook filtert als tweede laag
        mee, dus een runtime-test alleen zou groen blijven nadat deze predicaten zijn
        weggehaald -- daarom wordt hier de GECOMPILEERDE SQL getoetst.
        """
        statement = _registry()._build_gap_statement(7, 50, 0, None)
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))

        for table in ("users", "role_required_skills", "skills", "employee_skills"):
            assert f"{table}.tenant_id = 7" in sql, (
                f"Geen eigen tenantvoorwaarde op {table}. Gemeten SQL:\n{sql}"
            )
        assert "users.deleted_at IS NULL" in sql, (
            "Gewiste gebruikers worden niet uitgesloten; een ex-medewerker houdt dan een "
            "kloof open."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestArgumentHandling:
    async def test_unsupported_filter_is_refused_for_this_tool_too(
        self, db_session: AsyncSession
    ) -> None:
        """`employee_id` blijft geweigerd: deze tool geeft per definitie geen personen terug."""
        result = await _registry().execute_hr_tool(TOOL, {"employee_id": 5}, tenant_id=1)

        assert result["success"] is False
        assert "employee_id" in result["error"]

    async def test_unreadable_limit_is_refused_instead_of_silently_defaulted(
        self, db_session: AsyncSession
    ) -> None:
        result = await _registry().execute_hr_tool(TOOL, {"limit": "abc"}, tenant_id=1)

        assert result["success"] is False
        assert "limit" in result["error"]

    async def test_tenant_id_must_come_from_the_context(self, db_session: AsyncSession) -> None:
        """Een ontbrekende of onzinnige tenant is een harde fout, geen lege uitkomst."""
        from src.core.tool_broker.exceptions import ToolExecutionException

        with pytest.raises(ToolExecutionException):
            await _registry().execute_hr_tool(TOOL, {}, tenant_id=0)
