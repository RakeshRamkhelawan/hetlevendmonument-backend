"""Een medewerker (rol `editor`) mag via een workflow taken aanmaken en wijzigen, met een smal eigen recht (brief 2026-10-23).

Besluit Rakesh 2026-10-23: "ja". `create_task` en `update_task` vragen sindsdien `tasks:write` in plaats van `tools:write`
(dat zou elke schrijftool openen, ook bestanden schrijven); `delete_task` blijft `tools:admin`. De rol `editor` krijgt
`tasks:write`; de rol `user` niet.

Echte rollen: de zaaier `ensure_default_roles` (als eigenaar), gebruikers via `user_roles`, en de controle draait onder de
applicatierol `sanskritisetu_app` (RLS afgedwongen). De provider roept de echte `starter_heeft_toolrecht` aan.

**Mutatiebewijs:** zie de eindmelding van de sessie (een regel per element).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from tests.integration.security.test_tools_rechten_uit_de_database_onder_de_applicatierol import (  # noqa: F401
    Gebruikers,
    _url,
    als_applicatierol,
    db,
    gebruikers,
)
from tests.integration.security.test_tools_rechten_uit_de_database_onder_de_applicatierol import (
    pytestmark as _pytestmark,
)

from src.core.services.rbac_service import RBACService
from src.core.tool_broker.workflow_identiteit import starter_heeft_toolrecht
from src.core.workflow.providers import ProductionToolBroker

pytestmark = _pytestmark


@pytest.mark.asyncio
class TestEenEditorMagTakenMakenEnWijzigen:
    async def test_een_editor_mag_een_taak_aanmaken(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        assert await starter_heeft_toolrecht(editor, "create_task", gebruikers.tenant_a) is True

    async def test_een_editor_mag_een_taak_wijzigen(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        assert await starter_heeft_toolrecht(editor, "update_task", gebruikers.tenant_a) is True

    async def test_een_editor_mag_taken_lezen(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        assert await starter_heeft_toolrecht(editor, "list_tasks", gebruikers.tenant_a) is True

    async def test_een_editor_mag_geen_taak_verwijderen(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        assert await starter_heeft_toolrecht(editor, "delete_task", gebruikers.tenant_a) is False


@pytest.mark.asyncio
class TestHetRechtIsSmal:
    async def test_een_editor_mag_geen_bestand_schrijven(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        """`tools:write` zit NIET in de rol editor: een andere schrijftool blijft geweigerd."""
        editor = str(gebruikers.per_rol["editor"])

        assert (
            await starter_heeft_toolrecht(editor, "local__write_file", gebruikers.tenant_a) is False
        )

    async def test_een_editor_mag_geen_personeelsgegevens_lezen(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        assert (
            await starter_heeft_toolrecht(editor, "query_hr_database", gebruikers.tenant_a) is False
        )

    async def test_een_gewone_gebruiker_mag_geen_taak_aanmaken(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        gewoon = str(gebruikers.per_rol["user"])

        assert await starter_heeft_toolrecht(gewoon, "create_task", gebruikers.tenant_a) is False

    async def test_een_gewone_gebruiker_mag_taken_lezen(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        gewoon = str(gebruikers.per_rol["user"])

        assert await starter_heeft_toolrecht(gewoon, "list_tasks", gebruikers.tenant_a) is True

    async def test_een_beheerder_mag_aanmaken_en_verwijderen(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        beheerder = str(gebruikers.per_rol["admin"])
        maken = await starter_heeft_toolrecht(beheerder, "create_task", gebruikers.tenant_a)
        verwijderen = await starter_heeft_toolrecht(beheerder, "delete_task", gebruikers.tenant_a)

        assert (maken, verwijderen) == (True, True)

    async def test_een_beheerder_van_een_andere_klant_krijgt_niets(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        vreemd = str(gebruikers.beheerder_van_b)

        assert await starter_heeft_toolrecht(vreemd, "create_task", gebruikers.tenant_a) is False


@pytest.mark.asyncio
class TestBestaandeKlantenKrijgenHetRechtZonderMigratie:
    async def test_ensure_default_roles_vult_het_recht_aan_bij_een_bestaande_editorrol(
        self, als_applicatierol: None, gebruikers: Gebruikers, db
    ) -> None:
        """Een klant die de rol `editor` al had (zonder `tasks:write`) krijgt het recht bij de volgende start."""
        editor = str(gebruikers.per_rol["editor"])
        with db.cursor() as cur:
            cur.execute(
                "DELETE FROM role_permissions WHERE resource = 'tasks' AND action = 'write' "
                "AND role_id IN (SELECT id FROM roles WHERE tenant_id = %s AND name = 'editor')",
                (gebruikers.tenant_a,),
            )
            cur.execute(
                "SELECT count(*) FROM roles WHERE tenant_id = %s AND name = 'editor'",
                (gebruikers.tenant_a,),
            )
            rollen_voor = cur.fetchone()[0]
        zonder = await starter_heeft_toolrecht(editor, "create_task", gebruikers.tenant_a)

        eigenaar = create_async_engine(_url(), poolclass=NullPool)
        try:
            async with AsyncSession(eigenaar) as sessie:
                await RBACService(sessie).ensure_default_roles(gebruikers.tenant_a)
                await sessie.commit()
        finally:
            await eigenaar.dispose()
        met = await starter_heeft_toolrecht(editor, "create_task", gebruikers.tenant_a)
        with db.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM roles WHERE tenant_id = %s AND name = 'editor'",
                (gebruikers.tenant_a,),
            )
            rollen_na = cur.fetchone()[0]

        # dezelfde ene rol (niet opnieuw aangemaakt), alleen het recht is erbij gekomen
        assert (zonder, met, rollen_voor, rollen_na) == (False, True, 1, 1)


@pytest.mark.asyncio
class TestDoorDeProviderMetEchteRollen:
    @staticmethod
    def _provider() -> tuple[ProductionToolBroker, MagicMock]:
        broker = MagicMock()
        broker.execute_tool = AsyncMock(return_value={"id": 1})
        provider = ProductionToolBroker()
        provider._dienst = broker
        return provider, broker

    async def test_de_createstap_van_een_editor_slaagt(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        provider, broker = self._provider()

        uitkomst = await provider.execute_tool(
            "create_task",
            {"title": "x"},
            tenant_id=gebruikers.tenant_a,
            starter=str(gebruikers.per_rol["editor"]),
        )

        assert (uitkomst["success"], broker.execute_tool.await_count) == (True, 1)

    async def test_de_deletestap_van_een_editor_faalt_en_raakt_de_broker_niet(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        provider, broker = self._provider()

        uitkomst = await provider.execute_tool(
            "delete_task",
            {"task_id": 1},
            tenant_id=gebruikers.tenant_a,
            starter=str(gebruikers.per_rol["editor"]),
        )

        assert (uitkomst["success"], broker.execute_tool.await_count) == (False, 0)

    async def test_de_createstap_van_een_gewone_gebruiker_faalt(
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
