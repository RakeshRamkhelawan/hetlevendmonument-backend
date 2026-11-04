"""Een AVG-wissing van de laatste beheerder gaat door en laat een spoor na (ADR-039, AVG art. 17).

Besluit regie 2026-10-10: een wettelijke wissing wordt NOOIT geblokkeerd door LAST_ADMIN. Maar de
tenant staat daarna zonder beheerder, en het platform moet dat kunnen zien om de klant een nieuwe
beheerder te geven. Gemeten tegen echte Postgres, met een wegwerpgebruiker (de bestaande
gebruikers worden nooit gewist of geanonimiseerd):

1. De wissing van de laatste beheerder SLAAGT, voor de zachte DSAR-wissing en voor de purge-actor.
   De HARDE DSAR-wissing staat hier bewust niet: die faalt vandaag voor elke gebruiker met een rol
   (`fk_user_roles_user_tenant`, gemeten 2026-10-11 met dit bestand) en dat is een eigen bevinding.
2. Zij laat een auditregel `tenant_zonder_beheerder` achter, met alleen het tenant-id.
3. Zij laat een WARNING achter.
4. Is er nog een andere beheerder, of was de gewiste geen beheerder: geen auditregel.

De telling is die van LAST_ADMIN (`RBACService._tenant_admin_ids`); er is geen tweede definitie.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import (  # noqa: F401
    COLLEGA,
    TENANT,
    _sql,
    rollen_hersteld,
)
from tests.integration.test_laatste_beheerder import beheerders_geisoleerd  # noqa: F401

AUDITACTIE = "tenant_zonder_beheerder"
WEGWERP_EMAIL = "wegwerp-beheerder@avg-wissing.invalid"


async def _ruim_gebruiker_op(user_id: int) -> None:
    """Verwijder een wegwerpgebruiker; de wissing liet auditregels achter die naar hem verwijzen."""
    await _sql("DELETE FROM audit_logs WHERE user_id = :u", u=user_id)
    await _sql("DELETE FROM user_roles WHERE user_id = :u", u=user_id)
    await _sql("DELETE FROM users WHERE id = :u", u=user_id)


async def _maak_wegwerpgebruiker(rol: str | None) -> int:
    for oud in (await _sql("SELECT id FROM users WHERE email = :e", e=WEGWERP_EMAIL)).all():
        await _ruim_gebruiker_op(int(oud[0]))
    rij = (
        await _sql(
            "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
            "VALUES (:e, 'x', true, false, :t) RETURNING id",
            e=WEGWERP_EMAIL,
            t=TENANT,
        )
    ).one()
    user_id = int(rij[0])
    if rol is not None:
        await _sql(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) "
            "SELECT :u, id, :t FROM roles WHERE tenant_id = :t AND name = :n",
            u=user_id,
            t=TENANT,
            n=rol,
        )
    return user_id


async def _auditregels() -> list[dict[str, Any]]:
    rijen = (
        await _sql(
            "SELECT resource, details, user_id FROM audit_logs "
            "WHERE tenant_id = :t AND action = :a ORDER BY id",
            t=TENANT,
            a=AUDITACTIE,
        )
    ).all()
    return [{"resource": r[0], "details": r[1], "user_id": r[2]} for r in rijen]


@pytest_asyncio.fixture
async def laatste_beheerder(beheerders_geisoleerd: None) -> AsyncGenerator[int, None]:
    """Een wegwerpgebruiker die de ENIGE actieve beheerder van tenant 1 is."""
    await _sql(
        "DELETE FROM audit_logs WHERE tenant_id = :t AND action = :a", t=TENANT, a=AUDITACTIE
    )
    user_id = await _maak_wegwerpgebruiker("admin")
    yield user_id
    await _ruim_gebruiker_op(user_id)
    await _sql(
        "DELETE FROM audit_logs WHERE tenant_id = :t AND action = :a", t=TENANT, a=AUDITACTIE
    )


async def _dsar_wis(user_id: int, *, hard: bool) -> Any:
    from src.core.database.database import db_manager
    from src.core.governance.dsar_service import DSARService

    async with db_manager.get_session() as session:
        return await DSARService(session).delete_user_data(
            user_id=str(user_id),
            tenant_id=TENANT,
            hard_delete=hard,
            requested_by_user_id=str(user_id),
            is_admin=hard,
        )


@pytest.mark.asyncio
@pytest.mark.integration
class TestWissingVanDeLaatsteBeheerder:
    async def test_a_soft_delete_of_the_last_admin_still_succeeds(
        self, laatste_beheerder: int
    ) -> None:
        resultaat = await _dsar_wis(laatste_beheerder, hard=False)

        assert resultaat.delete_type == "soft"

    async def test_a_soft_delete_of_the_last_admin_leaves_an_audit_line(
        self, laatste_beheerder: int
    ) -> None:
        await _dsar_wis(laatste_beheerder, hard=False)

        assert [r["resource"] for r in await _auditregels()] == [f"tenant:{TENANT}"]

    async def test_the_purge_actor_on_the_last_admin_leaves_an_audit_line(
        self, laatste_beheerder: int
    ) -> None:
        from src.core.actors.gdpr_purge import _run_purge

        await _run_purge(laatste_beheerder, TENANT, "all")

        assert [r["resource"] for r in await _auditregels()] == [f"tenant:{TENANT}"]

    async def test_a_profile_purge_on_the_last_admin_leaves_an_audit_line(
        self, laatste_beheerder: int
    ) -> None:
        from src.core.actors.gdpr_purge import _run_purge

        await _run_purge(laatste_beheerder, TENANT, "profile")

        assert len(await _auditregels()) == 1

    async def test_a_messages_only_purge_leaves_no_audit_line(self, laatste_beheerder: int) -> None:
        """Scope `messages` laat de gebruiker en zijn rol staan: de tenant houdt zijn beheerder."""
        from src.core.actors.gdpr_purge import _run_purge

        await _run_purge(laatste_beheerder, TENANT, "messages")

        assert await _auditregels() == []

    async def test_the_audit_line_carries_the_tenant_and_no_personal_data(
        self, laatste_beheerder: int
    ) -> None:
        await _dsar_wis(laatste_beheerder, hard=False)

        regel = (await _auditregels())[0]
        assert regel["user_id"] is None
        assert WEGWERP_EMAIL not in str(regel["details"])
        assert regel["details"]["tenant_id"] == TENANT

    async def test_the_deletion_leaves_a_warning(
        self, laatste_beheerder: int, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            await _dsar_wis(laatste_beheerder, hard=False)

        assert any(
            r.levelno == logging.WARNING and AUDITACTIE in r.getMessage() for r in caplog.records
        )

    async def test_the_warning_names_no_person(
        self, laatste_beheerder: int, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            await _dsar_wis(laatste_beheerder, hard=False)

        berichten = " ".join(r.getMessage() for r in caplog.records if AUDITACTIE in r.getMessage())
        assert WEGWERP_EMAIL not in berichten


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeMetingBlokkeertDeWissingNooit:
    async def test_a_failing_measurement_does_not_stop_the_deletion(
        self, laatste_beheerder: int
    ) -> None:
        with patch(
            "src.core.governance.dsar_service.is_laatste_beheerder",
            new=AsyncMock(side_effect=RuntimeError("meting stuk")),
        ):
            resultaat = await _dsar_wis(laatste_beheerder, hard=False)

        assert resultaat.delete_type == "soft"

    async def test_a_failing_measurement_leaves_no_audit_line(self, laatste_beheerder: int) -> None:
        with patch(
            "src.core.governance.dsar_service.is_laatste_beheerder",
            new=AsyncMock(side_effect=RuntimeError("meting stuk")),
        ):
            await _dsar_wis(laatste_beheerder, hard=False)

        assert await _auditregels() == []

    async def test_a_repeated_purge_leaves_one_audit_line(self, laatste_beheerder: int) -> None:
        from src.core.actors.gdpr_purge import _run_purge

        await _run_purge(laatste_beheerder, TENANT, "all")
        await _run_purge(laatste_beheerder, TENANT, "all")

        assert len(await _auditregels()) == 1

    async def test_the_purge_leaves_a_warning(
        self, laatste_beheerder: int, caplog: pytest.LogCaptureFixture
    ) -> None:
        from src.core.actors.gdpr_purge import _run_purge

        with caplog.at_level(logging.WARNING):
            await _run_purge(laatste_beheerder, TENANT, "all")

        assert any(
            r.levelno == logging.WARNING and AUDITACTIE in r.getMessage() for r in caplog.records
        )


@pytest.mark.asyncio
@pytest.mark.integration
class TestWissingMetNogEenBeheerder:
    async def test_deleting_an_admin_while_another_remains_leaves_no_audit_line(
        self, laatste_beheerder: int
    ) -> None:
        await _sql(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) "
            "SELECT :u, id, :t FROM roles WHERE tenant_id = :t AND name = 'admin'",
            u=COLLEGA,
            t=TENANT,
        )

        await _dsar_wis(laatste_beheerder, hard=False)

        assert await _auditregels() == []

    async def test_a_platform_superuser_does_not_count_as_another_admin(
        self, laatste_beheerder: int
    ) -> None:
        """Dezelfde telling als LAST_ADMIN: de platform-superuser beheert het platform, niet de tenant."""
        await _sql(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) "
            "SELECT :u, id, :t FROM roles WHERE tenant_id = :t AND name = 'admin'",
            u=COLLEGA,
            t=TENANT,
        )
        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=COLLEGA)

        await _dsar_wis(laatste_beheerder, hard=False)

        assert len(await _auditregels()) == 1

    async def test_deleting_an_ordinary_user_leaves_no_audit_line(
        self, laatste_beheerder: int
    ) -> None:
        gewone = await _maak_wegwerpgebruiker(None)
        try:
            await _dsar_wis(gewone, hard=True)
        finally:
            await _ruim_gebruiker_op(gewone)

        assert await _auditregels() == []
