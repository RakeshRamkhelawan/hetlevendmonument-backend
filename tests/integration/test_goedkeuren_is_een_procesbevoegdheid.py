"""Goedkeuren is een procesbevoegdheid, geen beheerdersrecht (ADR-039 F1/F2/F7).

Besluit Rakesh 2026-10-09: "Een beheerder heeft niets te maken met een proces dat geaccordeerd
moet worden" en "in een klein bedrijf mag 1 persoon alle rollen beslaan".

Wat deze test over de ECHTE routes en de database-RBAC vaststelt:

1. Een beheerder (rol `admin`, `*:*`) zonder de rol `goedkeurder` keurt een debiteurenticket NIET
   goed: 403, en er gaat niets weg.
2. Een gebruiker met alleen `goedkeurder` keurt het wel goed.
3. Een persoon met admin EN goedkeurder keurt het voorstel van een ANDER goed; zijn eigen
   voorstel alleen als vier ogen uit staat (bestaand gedrag, ongewijzigd).
4. Een platform-superuser zonder procesrecht in de tenant keurt niets goed (F7).
5. `/pending` en `reject` vragen hetzelfde recht.
6. Het recht hangt aan de ACTIE van het ticket: `hr:approve` is geen `receivables:approve`.
7. `*:*` van admin geeft geen `receivables:approve` (de actie `approve` telt alleen als er een rij
   met precies die resource en actie is); gewone rechten via de wildcard blijven werken.

**Wat echt is en wat niet:** zoals `scenarios/test_scenario_5_betalingsherinnering.py` -- Postgres
op netwerkpoort 5455, de Council, de HITL-routes en de broker zijn echt; vervangen zijn het
taalmodel, `get_current_user` (de `roles` in het tokenobject doen er voor de beslissing NIET toe:
de rechten komen uit de database) en de CSRF-controle.

Wat NIET gemeten is: een draaiende applicatie met scherm, en de gatekeeper-route met een echt
`hitl_requests`-ticket (die staat in de unit-tests naast `test_gatekeeper_hitl_requires_an_approver`).
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

TENANT = 1
AANVRAGER = 1
COLLEGA = 101
# Een gewone gebruiker (geen superuser). COLLEGA (101) is in de seed een platformbeheerder; sinds f9971f04
# (2026-10-19) mag wie geen `system_admin` is de rollen van een platformbeheerder niet wijzigen (fail-secure,
# besluit regie 2026-10-26), dus een intrekking door AANVRAGER op COLLEGA wordt geweigerd. De intrekkings-tests
# hieronder gebruiken daarom een gewone collega als doel.
GEWONE_COLLEGA = 2
_TICKET = re.compile(r"goedkeuringsticket aangemaakt: (hitl_[0-9a-f]+)")


async def _sql(query: str, **params: Any) -> Any:
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        result = await session.execute(text(query), params)
        await session.commit()
        return result


async def _zet_vier_ogen(aan: bool) -> None:
    waarde = '{"four_eyes_actions": ["send_payment_reminder"]}' if aan else "{}"
    await _sql("UPDATE tenants SET settings = CAST(:s AS JSON) WHERE id = :t", s=waarde, t=TENANT)


async def _zaai_standaardrollen() -> None:
    from src.core.database.bypass_session import adopt_tenant
    from src.core.database.database import db_manager
    from src.core.services.rbac_service import RBACService

    async with db_manager.get_session() as session:
        async with adopt_tenant(session, TENANT):
            await RBACService(session).ensure_default_roles(TENANT)
        await session.commit()


async def _zet_rollen(user_id: int, rolnamen: list[str]) -> None:
    """Vervang de databaserollen van de gebruiker door precies deze (de enige bron van rechten)."""
    await _sql("DELETE FROM user_roles WHERE user_id = :u AND tenant_id = :t", u=user_id, t=TENANT)
    for naam in rolnamen:
        await _sql(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) "
            "SELECT :u, id, :t FROM roles WHERE tenant_id = :t AND name = :n",
            u=user_id,
            t=TENANT,
            n=naam,
        )


@pytest_asyncio.fixture
async def rollen_hersteld() -> AsyncGenerator[None, None]:
    """Bewaar de gezaaide rollen van beide gebruikers en zet ze na de test terug."""
    await _zaai_standaardrollen()
    oud = list(
        (
            await _sql(
                "SELECT user_id, role_id FROM user_roles WHERE tenant_id = :t "
                "AND user_id IN (:a, :c, :g)",
                t=TENANT,
                a=AANVRAGER,
                c=COLLEGA,
                g=GEWONE_COLLEGA,
            )
        ).all()
    )
    yield
    await _sql(
        "DELETE FROM user_roles WHERE tenant_id = :t AND user_id IN (:a, :c, :g)",
        t=TENANT,
        a=AANVRAGER,
        c=COLLEGA,
        g=GEWONE_COLLEGA,
    )
    for user_id, role_id in oud:
        await _sql(
            "INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (:u, :r, :t)",
            u=user_id,
            r=role_id,
            t=TENANT,
        )


@pytest_asyncio.fixture
async def debiteur(rollen_hersteld: None) -> AsyncGenerator[int, None]:
    from src.core.database.database import db_manager
    from src.core.repositories.receivable_repository import NewReceivable, ReceivableRepository

    async with db_manager.get_session() as session:
        rij = await ReceivableRepository(session).add(
            TENANT,
            NewReceivable(
                customer_name="Bakkerij De Korst",
                customer_email="administratie@dekorst.example",
                invoice_number="F-2026-042",
                amount=Decimal("1250.50"),
                currency="EUR",
                due_date=date(2026, 9, 1),
            ),
        )
        await session.commit()
        rid = rij.id
    yield rid
    await _sql("DELETE FROM outgoing_messages WHERE tenant_id = :t", t=TENANT)
    await _sql("DELETE FROM hitl_tickets WHERE tenant_id = :t", t=TENANT)
    await _sql("DELETE FROM receivables WHERE id = :r", r=rid)
    await _zet_vier_ogen(False)


@pytest_asyncio.fixture
async def debiteuren_ticket(debiteur: int) -> str:
    """Een wachtend debiteurenticket (send_payment_reminder, eist receivables:approve)."""
    return await _agent_vraagt_aan(debiteur)


async def _agent_vraagt_aan(receivable_id: int) -> str:
    from src.core.als.agents.skills.dunning import DunningSkill

    agent = DunningSkill(tenant_id=TENANT)
    model = AsyncMock()
    model.generate = AsyncMock(
        return_value=(
            "Factuur F-2026-042 is over de vervaldatum.\n"
            f'TOOL_CALL: send_payment_reminder {{"receivable_id": {receivable_id}, '
            '"kind": "herinnering"}'
        )
    )

    async def _model() -> Any:
        return model

    agent._get_llm_service = _model  # type: ignore[method-assign]
    resultaat = await agent.execute_with_manifest_prompt(
        {"task": "Stuur een herinnering voor F-2026-042"}, initiated_by_user_id=AANVRAGER
    )
    fouten = " ".join(str(f.get("error")) for f in resultaat.result_data.get("errors", []))
    gevonden = _TICKET.search(fouten)
    assert gevonden, f"geen goedkeuringsticket; de agent meldde: {fouten}"
    return gevonden.group(1)


def _beslisser(user_id: int, *, superuser: bool = False) -> Any:
    """Het tokenobject zegt `admin`: dat mag voor de beslissing niets uitmaken."""
    from src.core.auth.auth_service import UserResponse

    return UserResponse(
        id=user_id,
        email=f"u{user_id}@integration.test",
        tenant_id=TENANT,
        roles=["admin"],
        is_superuser=superuser,
    )


async def _vraag(
    integration_app: Any,
    user_id: int,
    methode: str,
    pad: str,
    body: dict[str, str] | None = None,
    *,
    superuser: bool = False,
) -> Any:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import db_manager, get_db
    from tests.integration.conftest import _build_test_token

    async def _db() -> AsyncGenerator[Any, None]:
        async with db_manager.get_session() as session:
            yield session

    async def _geen_csrf() -> None:
        return None

    overrides = {
        get_db: _db,
        get_current_user: lambda: _beslisser(user_id, superuser=superuser),
        validate_csrf_token: _geen_csrf,
    }
    token = _build_test_token(
        user_id=user_id, email=f"u{user_id}@integration.test", tenant_id=TENANT
    )
    integration_app.dependency_overrides.update(overrides)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=integration_app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            return await client.request(methode, f"/api/v1/tools/hitl/{pad}", json=body)
    finally:
        for dep in overrides:
            integration_app.dependency_overrides.pop(dep, None)


async def _berichten() -> list[Any]:
    return list(
        (await _sql("SELECT recipient FROM outgoing_messages WHERE tenant_id = :t", t=TENANT)).all()
    )


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeBeheerderKeurtNietGoed:
    async def test_an_admin_without_the_approver_role_gets_403_and_nothing_is_sent(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        await _zet_rollen(COLLEGA, ["admin"])

        antwoord = await _vraag(integration_app, COLLEGA, "POST", "approve", {"ticket_ref": ref})

        assert antwoord.status_code == 403, antwoord.text
        assert await _berichten() == []

    async def test_an_admin_without_the_approver_role_cannot_reject_either(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        await _zet_rollen(COLLEGA, ["admin"])

        antwoord = await _vraag(
            integration_app, COLLEGA, "POST", "reject", {"ticket_ref": ref, "reason": "dit mag niet versturen"}
        )

        assert antwoord.status_code == 403, antwoord.text

    async def test_an_admin_does_not_see_a_receivables_ticket_in_the_pending_list(
        self, debiteuren_ticket: str, integration_app: Any
    ) -> None:
        """De beheerder heeft `config:approve` en mag dus de lijst openen, maar ziet alleen
        tickets die hij mag beslissen: de debiteurenbrief (ONBEWERKTE tool_input) is niet van hem."""
        await _zet_rollen(COLLEGA, ["admin"])

        antwoord = await _vraag(integration_app, COLLEGA, "GET", "pending")

        assert antwoord.status_code == 200, antwoord.text
        assert debiteuren_ticket not in antwoord.text

    async def test_a_user_without_any_approval_right_cannot_list_the_pending_tickets(
        self, debiteur: int, integration_app: Any
    ) -> None:
        await _zet_rollen(COLLEGA, ["user"])

        antwoord = await _vraag(integration_app, COLLEGA, "GET", "pending")

        assert antwoord.status_code == 403, antwoord.text

    async def test_a_platform_superuser_without_the_process_right_gets_403(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        await _zet_rollen(COLLEGA, [])

        antwoord = await _vraag(
            integration_app, COLLEGA, "POST", "approve", {"ticket_ref": ref}, superuser=True
        )

        assert antwoord.status_code == 403, antwoord.text
        assert await _berichten() == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeGoedkeurderKeurtWelGoed:
    async def test_a_user_with_only_the_approver_role_approves_and_the_letter_is_created(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        await _zet_rollen(COLLEGA, ["goedkeurder"])

        antwoord = await _vraag(integration_app, COLLEGA, "POST", "approve", {"ticket_ref": ref})

        assert antwoord.status_code == 200, antwoord.text
        assert len(await _berichten()) == 1

    async def test_the_approver_role_sees_the_receivables_ticket_in_the_pending_list(
        self, debiteuren_ticket: str, integration_app: Any
    ) -> None:
        await _zet_rollen(COLLEGA, ["goedkeurder"])

        antwoord = await _vraag(integration_app, COLLEGA, "GET", "pending")

        assert antwoord.status_code == 200, antwoord.text
        assert debiteuren_ticket in antwoord.text

    async def test_a_person_with_admin_and_approver_approves_the_proposal_of_someone_else(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        await _zet_rollen(COLLEGA, ["admin", "goedkeurder"])

        antwoord = await _vraag(integration_app, COLLEGA, "POST", "approve", {"ticket_ref": ref})

        assert antwoord.status_code == 200, antwoord.text

    async def test_a_small_company_one_person_may_approve_their_own_proposal_when_four_eyes_is_off(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        await _zet_rollen(AANVRAGER, ["admin", "goedkeurder"])

        antwoord = await _vraag(integration_app, AANVRAGER, "POST", "approve", {"ticket_ref": ref})

        assert antwoord.status_code == 200, antwoord.text

    async def test_four_eyes_on_still_refuses_the_own_proposal_even_with_the_approver_role(
        self, debiteur: int, integration_app: Any
    ) -> None:
        await _zet_vier_ogen(True)
        ref = await _agent_vraagt_aan(debiteur)
        await _zet_rollen(AANVRAGER, ["admin", "goedkeurder"])

        antwoord = await _vraag(integration_app, AANVRAGER, "POST", "approve", {"ticket_ref": ref})

        assert antwoord.status_code == 403, antwoord.text
        assert await _berichten() == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestHetRechtHangtAanDeActie:
    async def test_the_hr_approval_right_does_not_approve_a_receivables_ticket(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        await _sql(
            "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
            "SELECT id, :t, 'hr', 'approve' FROM roles WHERE tenant_id = :t AND name = 'debiteuren' "
            "AND NOT EXISTS (SELECT 1 FROM role_permissions p WHERE p.role_id = roles.id "
            "AND p.resource = 'hr' AND p.action = 'approve')",
            t=TENANT,
        )
        try:
            await _zet_rollen(COLLEGA, ["debiteuren"])

            antwoord = await _vraag(
                integration_app, COLLEGA, "POST", "approve", {"ticket_ref": ref}
            )

            assert antwoord.status_code == 403, antwoord.text
        finally:
            await _sql(
                "DELETE FROM role_permissions WHERE resource = 'hr' AND action = 'approve' "
                "AND role_id IN (SELECT id FROM roles WHERE tenant_id = :t "
                "AND name = 'debiteuren')",
                t=TENANT,
            )


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeWildcardGeeftGeenApprove:
    async def _heeft(self, user_id: int, recht: str) -> bool:
        from src.core.database.bypass_session import adopt_tenant
        from src.core.database.database import db_manager
        from src.core.services.rbac_service import RBACService

        async with db_manager.get_session() as session:
            async with adopt_tenant(session, TENANT):
                return await RBACService(session).user_has_permission(
                    user_id, recht, tenant_id=TENANT
                )

    async def test_admin_wildcard_does_not_include_receivables_approve(
        self, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(COLLEGA, ["admin"])

        assert await self._heeft(COLLEGA, "receivables:approve") is False

    async def test_admin_wildcard_does_not_include_hr_approve(self, rollen_hersteld: None) -> None:
        await _zet_rollen(COLLEGA, ["admin"])

        assert await self._heeft(COLLEGA, "hr:approve") is False

    async def test_admin_wildcard_still_grants_ordinary_rights(self, rollen_hersteld: None) -> None:
        await _zet_rollen(COLLEGA, ["admin"])

        assert await self._heeft(COLLEGA, "receivables:read") is True

    async def test_the_approver_role_has_exactly_its_explicit_right(
        self, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(COLLEGA, ["goedkeurder"])

        assert await self._heeft(COLLEGA, "receivables:approve") is True

    async def test_the_approver_role_does_not_grant_hr_approve(self, rollen_hersteld: None) -> None:
        await _zet_rollen(COLLEGA, ["goedkeurder"])

        assert await self._heeft(COLLEGA, "hr:approve") is False

    async def test_the_hr_approver_role_has_hr_approve(self, rollen_hersteld: None) -> None:
        await _zet_rollen(COLLEGA, ["goedkeurder_hr"])

        assert await self._heeft(COLLEGA, "hr:approve") is True

    async def test_the_hr_approver_role_does_not_grant_receivables_approve(
        self, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(COLLEGA, ["goedkeurder_hr"])

        assert await self._heeft(COLLEGA, "receivables:approve") is False

    async def test_a_person_with_admin_and_hr_approver_roles_has_hr_approve(
        self, rollen_hersteld: None
    ) -> None:
        """Een persoon met admin EN goedkeurder_hr heeft hr:approve (klein bedrijf, alle rollen)."""
        await _zet_rollen(COLLEGA, ["admin", "goedkeurder_hr"])

        assert await self._heeft(COLLEGA, "hr:approve") is True


    async def test_the_approver_role_has_the_general_approval_right(
        self, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(COLLEGA, ["goedkeurder"])

        assert await self._heeft(COLLEGA, "governance:approve") is True

    async def test_admin_wildcard_does_not_include_the_general_approval_right(
        self, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(COLLEGA, ["admin"])

        assert await self._heeft(COLLEGA, "governance:approve") is False

    async def test_the_admin_role_has_the_explicit_config_right(
        self, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(COLLEGA, ["admin"])

        assert await self._heeft(COLLEGA, "config:approve") is True

    async def test_the_approver_role_does_not_have_the_config_right(
        self, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(COLLEGA, ["goedkeurder"])

        assert await self._heeft(COLLEGA, "config:approve") is False

    async def test_a_user_without_roles_has_no_config_right(self, rollen_hersteld: None) -> None:
        await _zet_rollen(COLLEGA, [])

        assert await self._heeft(COLLEGA, "config:approve") is False


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeToewijzingVanEenRolWordtMetToewijzerGelogd:
    """Een persoon mag alle rollen hebben, maar bewust en gelogd: WIE gaf de rol."""

    async def _wijs_toe(self, assigned_by: int | None) -> Any:
        from unittest.mock import AsyncMock, patch

        from src.core.database.bypass_session import adopt_tenant
        from src.core.database.database import db_manager
        from src.core.services.rbac_service import RBACService

        emit = AsyncMock()
        async with db_manager.get_session() as session:
            async with adopt_tenant(session, TENANT):
                with patch("src.core.services.rbac_service.governance_bus.emit", emit):
                    ok = await RBACService(session).assign_role(
                        COLLEGA, "goedkeurder", TENANT, assigned_by=assigned_by
                    )
        assert ok is True
        return emit.await_args.args[0]

    async def test_the_event_records_who_assigned_the_role(self, rollen_hersteld: None) -> None:
        await _zet_rollen(COLLEGA, [])

        event = await self._wijs_toe(AANVRAGER)

        assert event.details["assigned_by"] == AANVRAGER

    async def test_the_event_still_names_the_target_and_the_role(
        self, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(COLLEGA, [])

        event = await self._wijs_toe(AANVRAGER)

        assert (event.entity_id, event.details["role_name"]) == (str(COLLEGA), "goedkeurder")

    async def test_a_self_assignment_is_recorded_as_such(self, rollen_hersteld: None) -> None:
        await _zet_rollen(AANVRAGER, [])
        from unittest.mock import AsyncMock, patch

        from src.core.database.bypass_session import adopt_tenant
        from src.core.database.database import db_manager
        from src.core.services.rbac_service import RBACService

        emit = AsyncMock()
        async with db_manager.get_session() as session:
            async with adopt_tenant(session, TENANT):
                with patch("src.core.services.rbac_service.governance_bus.emit", emit):
                    await RBACService(session).assign_role(
                        AANVRAGER, "goedkeurder", TENANT, assigned_by=AANVRAGER
                    )

        event = emit.await_args.args[0]
        assert (event.entity_id, event.details["assigned_by"]) == (str(AANVRAGER), AANVRAGER)

    async def test_a_system_assignment_has_no_assigner(self, rollen_hersteld: None) -> None:
        await _zet_rollen(COLLEGA, [])

        event = await self._wijs_toe(None)

        assert event.details["assigned_by"] is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestHetIntrekkenVanEenRolWordtMetIntrekkerGelogd:
    """Ook het afnemen van een rol is bewust en gelogd: WIE nam de rol weg."""

    async def _trek_in(self, revoked_by: int | None, doel: int = GEWONE_COLLEGA) -> Any:
        from unittest.mock import AsyncMock, patch

        from src.core.database.bypass_session import adopt_tenant
        from src.core.database.database import db_manager
        from src.core.services.rbac_service import RBACService

        emit = AsyncMock()
        async with db_manager.get_session() as session:
            async with adopt_tenant(session, TENANT):
                with patch("src.core.services.rbac_service.governance_bus.emit", emit):
                    ok = await RBACService(session).revoke_role(
                        doel, "goedkeurder", TENANT, revoked_by=revoked_by
                    )
        assert ok is True
        return emit.await_args.args[0]

    async def test_the_event_records_who_revoked_the_role(self, rollen_hersteld: None) -> None:
        await _zet_rollen(GEWONE_COLLEGA, ["goedkeurder"])

        event = await self._trek_in(AANVRAGER)

        assert (event.user_id, event.details["revoked_by"]) == (AANVRAGER, AANVRAGER)

    async def test_the_event_still_names_the_target_and_the_role(
        self, rollen_hersteld: None
    ) -> None:
        await _zet_rollen(GEWONE_COLLEGA, ["goedkeurder"])

        event = await self._trek_in(AANVRAGER)

        assert (event.entity_id, event.details["role_name"]) == (str(GEWONE_COLLEGA), "goedkeurder")

    async def test_revoking_from_a_platform_admin_is_refused_without_system_admin(
        self, rollen_hersteld: None
    ) -> None:
        """Fail-secure (f9971f04, besluit regie 2026-10-26): AANVRAGER is geen system_admin, COLLEGA is een
        platformbeheerder (seed-superuser): de intrekking wordt geweigerd en er wordt niets gelogd."""
        from src.core.services.rbac_service import PlatformRoleNotAllowedError

        await _zet_rollen(COLLEGA, ["goedkeurder"])

        with pytest.raises(PlatformRoleNotAllowedError):
            await self._trek_in(AANVRAGER, doel=COLLEGA)

    async def test_a_self_revocation_is_recorded_as_such(self, rollen_hersteld: None) -> None:
        await _zet_rollen(AANVRAGER, ["goedkeurder"])

        event = await self._trek_in(AANVRAGER, doel=AANVRAGER)

        assert (event.entity_id, event.details["revoked_by"]) == (str(AANVRAGER), AANVRAGER)

    async def test_a_system_revocation_has_no_revoker(self, rollen_hersteld: None) -> None:
        await _zet_rollen(GEWONE_COLLEGA, ["goedkeurder"])

        event = await self._trek_in(None)

        assert event.details["revoked_by"] is None
