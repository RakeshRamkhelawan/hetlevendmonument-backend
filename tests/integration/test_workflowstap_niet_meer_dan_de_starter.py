"""Een workflowstap mag niet meer dan de mens die de workflow startte (brief 2026-10-23).

Echte rollen: de zaaier `ensure_default_roles` (als eigenaar), gebruikers via `user_roles`, en de controle draait
onder de applicatierol `sanskritisetu_app` (RLS afgedwongen), zoals een worker dat doet. GEEN gepatchte
permissiecontrole: de provider roept de echte `starter_heeft_toolrecht` aan, die de echte `role_permissions` leest.

Wat de standaardrollen zijn (gemeten in `RBACService.ensure_default_roles`): `admin` heeft `*:*`, `editor` heeft
`workflows:*`, `tools:read` en sinds 2026-10-23 `tasks:write` (besluit Rakesh; zie
`test_medewerker_mag_via_workflow_taken_maken.py`), `user` heeft alleen `tools:read`. Een starter met alleen leesrecht
(`user`) kan een workflow starten maar zelf geen taak aanmaken; de workflow mocht dat tot 4a3e258d wel voor hem doen.

**Mutatiebewijs:** zie de eindmelding van de sessie (een regel per element).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from tests.integration.security.test_tools_rechten_uit_de_database_onder_de_applicatierol import (  # noqa: F401
    Gebruikers,
    als_applicatierol,
    db,
    gebruikers,
)
from tests.integration.security.test_tools_rechten_uit_de_database_onder_de_applicatierol import (
    pytestmark as _pytestmark,
)

from src.core.tool_broker.workflow_identiteit import starter_heeft_toolrecht
from src.core.workflow.providers import ProductionToolBroker

pytestmark = _pytestmark


@pytest.mark.asyncio
class TestDeStarterBepaaltWatDeStapMag:
    async def test_een_starter_met_alleen_leesrecht_mag_geen_taak_aanmaken(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        lezer = str(gebruikers.per_rol["user"])

        assert await starter_heeft_toolrecht(lezer, "create_task", gebruikers.tenant_a) is False

    async def test_een_starter_met_alleen_leesrecht_mag_geen_taak_wijzigen(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        lezer = str(gebruikers.per_rol["user"])

        assert await starter_heeft_toolrecht(lezer, "update_task", gebruikers.tenant_a) is False

    async def test_een_starter_met_leesrecht_mag_taken_lezen(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        assert await starter_heeft_toolrecht(editor, "list_tasks", gebruikers.tenant_a) is True

    async def test_een_starter_met_schrijfrecht_mag_een_taak_aanmaken(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        beheerder = str(gebruikers.per_rol["admin"])

        assert await starter_heeft_toolrecht(beheerder, "create_task", gebruikers.tenant_a) is True

    async def test_een_recht_dat_na_het_starten_is_ingetrokken_telt_niet_meer(
        self, als_applicatierol: None, gebruikers: Gebruikers, db
    ) -> None:
        beheerder = gebruikers.per_rol["admin"]
        voor = await starter_heeft_toolrecht(str(beheerder), "create_task", gebruikers.tenant_a)
        with db.cursor() as cur:
            cur.execute("DELETE FROM user_roles WHERE user_id = %s", (beheerder,))

        na = await starter_heeft_toolrecht(str(beheerder), "create_task", gebruikers.tenant_a)

        assert (voor, na) == (True, False)

    async def test_een_starter_uit_een_andere_klant_krijgt_niets(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        vreemd = str(gebruikers.beheerder_van_b)

        assert await starter_heeft_toolrecht(vreemd, "list_tasks", gebruikers.tenant_a) is False

    @pytest.mark.parametrize("starter", [None, "", "  ", "systeem", "12abc", "-3", "0"])
    async def test_geen_mens_geen_toolstap(
        self, als_applicatierol: None, gebruikers: Gebruikers, starter: str | None
    ) -> None:
        assert await starter_heeft_toolrecht(starter, "list_tasks", gebruikers.tenant_a) is False

    async def test_een_tool_zonder_vereist_recht_wordt_geweigerd(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        beheerder = str(gebruikers.per_rol["admin"])

        assert (
            await starter_heeft_toolrecht(beheerder, "bestaat_niet", gebruikers.tenant_a) is False
        )


@pytest.mark.asyncio
class TestDoorDeProviderMetEchteRollen:
    @staticmethod
    def _provider() -> tuple[ProductionToolBroker, MagicMock]:
        broker = MagicMock()
        broker.execute_tool = AsyncMock(return_value={"id": 1})
        provider = ProductionToolBroker()
        provider._dienst = broker
        return provider, broker

    async def test_de_stap_van_een_leesstarter_faalt_en_de_broker_blijft_ongemoeid(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        provider, broker = self._provider()

        uitkomst = await provider.execute_tool(
            "create_task",
            {"title": "x"},
            tenant_id=gebruikers.tenant_a,
            starter=str(gebruikers.per_rol["user"]),
        )

        assert (uitkomst["success"], broker.execute_tool.await_count) == (False, 0)

    async def test_de_stap_van_een_starter_met_schrijfrecht_slaagt(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        provider, broker = self._provider()

        uitkomst = await provider.execute_tool(
            "create_task",
            {"title": "x"},
            tenant_id=gebruikers.tenant_a,
            starter=str(gebruikers.per_rol["admin"]),
        )

        assert (uitkomst["success"], broker.execute_tool.await_count) == (True, 1)
