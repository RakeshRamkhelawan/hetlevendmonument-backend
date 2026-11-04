"""AVG-wissen wacht 30 dagen en is in te trekken; de werkgever kan een medewerker laten wissen.

Besluit Rakesh 2026-10-12 ("akkoord"): A) de purge na `POST /api/gdpr/delete-all` wacht 30 dagen en
is binnen die tijd in te trekken; B) `POST /api/gdpr/users/{user_id}/erase` laat de werkgever EEN
medewerker wissen, met dezelfde 30 dagen en dezelfde intrekking.

Gemeten tegen echte Postgres, in een verse tenant (beheerder, medewerker, collega) en met een
gebruiker in tenant 2 als controlegroep. De tijd wordt gesimuleerd door `deletion_scheduled_for` in
het verleden te zetten; de planner (`run_avg_purge_vervallen`) plant dan de purges in, en de test
draait die zoals een worker dat zou doen.

De toestand staat in de database (`users.is_active`, `deleted_at`, `deletion_scheduled_for`): die
overleeft een herstart van een worker, anders dan een Dramatiq-vertraging van 30 dagen in Redis.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio

from tests.integration.test_avg_wissen_werkt_echt import (
    Persoon,
    _maak_gebruiker,
    _ruim_op,
    _tel,
    _vul,
)
from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import _sql
from tests.integration.test_laatste_beheerder import _aanroep

ANDERE_TENANT = 2
EMAIL_BEHEERDER = "avg30-beheerder@avg30.invalid"
EMAIL_MEDEWERKER = "avg30-medewerker@avg30.invalid"
EMAIL_COLLEGA = "avg30-collega@avg30.invalid"
EMAIL_VREEMD = "avg30-vreemd@avg30.invalid"
DAGEN = 30


async def _vervang_rol(user_id: int, tenant_id: int, rol: str) -> None:
    await _sql("DELETE FROM user_roles WHERE user_id = :u", u=user_id)
    await _sql(
        "INSERT INTO user_roles (user_id, role_id, tenant_id) "
        "SELECT :u, id, :t FROM roles WHERE tenant_id = :t AND name = :n",
        u=user_id,
        t=tenant_id,
        n=rol,
    )


@pytest_asyncio.fixture
async def omgeving() -> AsyncGenerator[tuple[int, Persoon, Persoon, Persoon, Persoon], None]:
    """Verse tenant met beheerder, medewerker en collega, plus een gebruiker in tenant 2."""
    await _sql("DELETE FROM tenants WHERE slug = 'avg30-tenant'")
    tenant_id = int(
        (
            await _sql(
                "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
                "VALUES ('AVG 30 dagen', 'avg30-tenant', true, 10, 10, 1) RETURNING id"
            )
        ).scalar_one()
    )
    for rol in ("admin", "medewerker"):
        await _sql(
            "INSERT INTO roles (tenant_id, name, is_active) VALUES (:t, :n, true)",
            t=tenant_id,
            n=rol,
        )
    beheerder = await _maak_gebruiker(EMAIL_BEHEERDER, tenant_id)
    medewerker = await _maak_gebruiker(EMAIL_MEDEWERKER, tenant_id)
    collega = await _maak_gebruiker(EMAIL_COLLEGA, tenant_id)
    vreemd = await _maak_gebruiker(EMAIL_VREEMD, ANDERE_TENANT)
    await _vervang_rol(beheerder.id, tenant_id, "admin")
    await _vervang_rol(medewerker.id, tenant_id, "medewerker")
    await _vervang_rol(collega.id, tenant_id, "medewerker")
    for p in (medewerker, collega, vreemd):
        await _vul(p)
    yield tenant_id, beheerder, medewerker, collega, vreemd
    for p in (beheerder, medewerker, collega, vreemd):
        await _ruim_op(p.id)
    await _sql("DELETE FROM roles WHERE tenant_id = :t", t=tenant_id)
    await _sql("DELETE FROM audit_logs WHERE tenant_id = :t", t=tenant_id)
    await _sql("DELETE FROM tenants WHERE id = :t", t=tenant_id)


def _token(user_id: int, email: str, tenant_id: int) -> str:
    from tests.integration.conftest import _build_test_token

    return _build_test_token(user_id=user_id, email=email, tenant_id=tenant_id)


async def _gebruiker(user_id: int) -> dict[str, Any]:
    rij = (
        await _sql(
            "SELECT email, is_active, deleted_at, deletion_scheduled_for FROM users WHERE id = :u",
            u=user_id,
        )
    ).one()
    return {"email": rij[0], "actief": rij[1], "deleted_at": rij[2], "gepland": rij[3]}


async def _auditacties(tenant_id: int) -> list[str]:
    rijen = (
        await _sql("SELECT action FROM audit_logs WHERE tenant_id = :t ORDER BY id", t=tenant_id)
    ).all()
    return [str(r[0]) for r in rijen]


async def _draai_planner_en_purges() -> list[tuple[int, int]]:
    """Laat de planner de vervallen purges inplannen en voer ze uit zoals een worker."""
    from src.core.actors.gdpr_purge import _run_purge_en_controleer
    from src.core.jobs.avg_purge_job import run_avg_purge_vervallen

    ingepland: list[dict[str, Any]] = []
    with patch(
        "src.core.jobs.avg_purge_job.purge_user_data",
        SimpleNamespace(send=lambda **kw: ingepland.append(kw)),
    ):
        await run_avg_purge_vervallen()
    for kw in ingepland:
        await _run_purge_en_controleer(
            kw["user_id"], kw["tenant_id"], kw.get("scope", "all"), alleen_indien_vervallen=True
        )
    return [(kw["user_id"], kw["tenant_id"]) for kw in ingepland]


async def _laat_de_termijn_verstrijken(tenant_id: int) -> None:
    await _sql(
        "UPDATE users SET deletion_scheduled_for = now() - interval '1 day' "
        "WHERE tenant_id = :t AND deletion_scheduled_for IS NOT NULL",
        t=tenant_id,
    )


async def _delete_all(app: Any, tenant_id: int, beheerder: Persoon) -> Any:
    return await _aanroep(
        app,
        _token(beheerder.id, EMAIL_BEHEERDER, tenant_id),
        "POST",
        "/api/gdpr/delete-all",
        {"delete_type": "soft", "confirmation_code": str(tenant_id)},
    )


async def _revoke_all(app: Any, tenant_id: int, beheerder: Persoon) -> Any:
    return await _aanroep(
        app,
        _token(beheerder.id, EMAIL_BEHEERDER, tenant_id),
        "POST",
        "/api/gdpr/delete-all/revoke",
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeleteAllWacht30Dagen:
    async def test_nothing_is_wiped_right_after_the_request(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving

        antwoord = await _delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text
        assert await _tel(medewerker, "cva_conversations") == 1

    async def test_the_users_are_inactive_but_not_anonymised(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving

        await _delete_all(integration_app, tenant_id, beheerder)

        gebruiker = await _gebruiker(medewerker.id)
        assert (gebruiker["actief"], gebruiker["email"]) == (False, EMAIL_MEDEWERKER)

    async def test_the_purge_is_planned_30_days_ahead(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving

        await _delete_all(integration_app, tenant_id, beheerder)

        gepland = (await _gebruiker(medewerker.id))["gepland"]
        verschil = gepland - datetime.now(timezone.utc)
        assert timedelta(days=DAGEN - 1) < verschil <= timedelta(days=DAGEN)

    async def test_no_purge_is_sent_to_the_queue_by_the_request(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        verzonden: list[Any] = []

        with patch(
            "src.core.api.v1.gdpr_compliance.erasure_router.purge_user_data",
            SimpleNamespace(send=lambda **kw: verzonden.append(kw)),
        ):
            await _delete_all(integration_app, tenant_id, beheerder)

        assert verzonden == []

    async def test_the_planner_ignores_a_term_that_has_not_expired(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)

        assert await _draai_planner_en_purges() == []

    async def test_after_the_term_the_purge_wipes_like_before(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _laat_de_termijn_verstrijken(tenant_id)

        await _draai_planner_en_purges()

        assert await _tel(medewerker, "cva_conversations") == 0

    async def test_after_the_term_every_user_of_the_tenant_is_anonymised(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, collega, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _laat_de_termijn_verstrijken(tenant_id)

        await _draai_planner_en_purges()

        mails = [(await _gebruiker(p.id))["email"] for p in (beheerder, medewerker, collega)]
        assert all(m.endswith("@purged.invalid") for m in mails)

    async def test_a_user_of_another_tenant_is_left_alone(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, vreemd = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _laat_de_termijn_verstrijken(tenant_id)

        await _draai_planner_en_purges()

        assert await _tel(vreemd, "cva_conversations") == 1

    async def test_the_planner_plans_a_purged_user_only_once(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _laat_de_termijn_verstrijken(tenant_id)
        await _draai_planner_en_purges()

        assert await _draai_planner_en_purges() == []


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeleteAllIntrekken:
    async def test_revoking_reactivates_the_users(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)

        antwoord = await _revoke_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text
        gebruiker = await _gebruiker(medewerker.id)
        assert (gebruiker["actief"], gebruiker["gepland"]) == (True, None)

    async def test_after_revoking_nothing_is_wiped(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _revoke_all(integration_app, tenant_id, beheerder)
        await _laat_de_termijn_verstrijken(tenant_id)

        await _draai_planner_en_purges()

        assert await _tel(medewerker, "cva_conversations") == 1

    async def test_revoking_leaves_an_audit_line(self, omgeving: Any, integration_app: Any) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)

        await _revoke_all(integration_app, tenant_id, beheerder)

        assert "gdpr_delete_all_revoked" in await _auditacties(tenant_id)

    async def test_a_user_who_was_already_inactive_stays_inactive(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, collega, _ = omgeving
        await _sql("UPDATE users SET is_active = false WHERE id = :u", u=collega.id)
        await _delete_all(integration_app, tenant_id, beheerder)

        await _revoke_all(integration_app, tenant_id, beheerder)

        assert (await _gebruiker(collega.id))["actief"] is False

    async def test_revoking_after_the_term_has_expired_is_refused(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _laat_de_termijn_verstrijken(tenant_id)

        antwoord = await _revoke_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 409


async def _erase(app: Any, tenant_id: int, wie: tuple[int, str], doel_id: int) -> Any:
    return await _aanroep(
        app, _token(wie[0], wie[1], tenant_id), "POST", f"/api/gdpr/users/{doel_id}/erase"
    )


async def _revoke_erase(app: Any, tenant_id: int, wie: tuple[int, str], doel_id: int) -> Any:
    return await _aanroep(
        app, _token(wie[0], wie[1], tenant_id), "POST", f"/api/gdpr/users/{doel_id}/erase/revoke"
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestEenMedewerkerWissen:
    async def test_the_administrator_can_request_it(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving

        antwoord = await _erase(
            integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id
        )

        assert antwoord.status_code == 200, antwoord.text

    async def test_only_that_person_becomes_inactive(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, collega, _ = omgeving

        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)

        assert [(await _gebruiker(p.id))["actief"] for p in (medewerker, collega)] == [False, True]

    async def test_nothing_is_wiped_right_away(self, omgeving: Any, integration_app: Any) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving

        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)

        assert await _tel(medewerker, "cva_conversations") == 1

    async def test_the_answer_names_the_planned_date(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving

        antwoord = await _erase(
            integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id
        )

        gepland = datetime.fromisoformat(antwoord.json()["scheduled_purge_date"])
        verschil = gepland - datetime.now(timezone.utc)
        assert timedelta(days=DAGEN - 1) < verschil <= timedelta(days=DAGEN)

    async def test_after_the_term_only_that_person_is_wiped(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, collega, vreemd = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)
        await _laat_de_termijn_verstrijken(tenant_id)

        ingepland = await _draai_planner_en_purges()

        assert ingepland == [(medewerker.id, tenant_id)]
        assert [await _tel(p, "cva_conversations") for p in (medewerker, collega, vreemd)] == [
            0,
            1,
            1,
        ]

    async def test_revoking_one_erasure_reactivates_that_person(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)

        antwoord = await _revoke_erase(
            integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id
        )

        assert antwoord.status_code == 200, antwoord.text
        gebruiker = await _gebruiker(medewerker.id)
        assert (gebruiker["actief"], gebruiker["gepland"]) == (True, None)

    async def test_a_revoked_erasure_wipes_nothing_after_the_term(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)
        await _revoke_erase(
            integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id
        )
        await _laat_de_termijn_verstrijken(tenant_id)

        assert await _draai_planner_en_purges() == []

    async def test_a_revoked_erasure_leaves_an_audit_line(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)

        await _revoke_erase(
            integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id
        )

        assert "gdpr_user_erase_revoked" in await _auditacties(tenant_id)

    async def test_a_user_of_another_tenant_is_404(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, vreemd = omgeving

        antwoord = await _erase(
            integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), vreemd.id
        )

        assert antwoord.status_code == 404

    async def test_the_other_tenant_user_is_untouched_after_the_404(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, vreemd = omgeving

        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), vreemd.id)

        assert (await _gebruiker(vreemd.id))["actief"] is True

    async def test_an_ordinary_user_is_403(self, omgeving: Any, integration_app: Any) -> None:
        tenant_id, _, medewerker, collega, _ = omgeving

        antwoord = await _erase(
            integration_app, tenant_id, (medewerker.id, EMAIL_MEDEWERKER), collega.id
        )

        assert antwoord.status_code == 403

    async def test_an_ordinary_user_changes_nothing(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, _, medewerker, collega, _ = omgeving

        await _erase(integration_app, tenant_id, (medewerker.id, EMAIL_MEDEWERKER), collega.id)

        assert (await _gebruiker(collega.id))["actief"] is True

    async def test_erasing_the_last_administrator_is_not_blocked_but_audited(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """De beheerder is de enige: de wissing gaat door en laat tenant_zonder_beheerder achter."""
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _vervang_rol(medewerker.id, tenant_id, "admin")
        # De aanvrager telt niet mee als tenantbeheerder (een platform-superuser, F7) maar blijft
        # actief: een uitgezet account mag sinds "uitgeschakeld is uitgeschakeld" geen verzoek meer doen.
        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=beheerder.id)

        antwoord = await _erase(
            integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id
        )

        assert antwoord.status_code == 200, antwoord.text
        assert "tenant_zonder_beheerder" in await _auditacties(tenant_id)

    async def test_erasing_the_last_administrator_leaves_a_warning(
        self,
        omgeving: Any,
        integration_app: Any,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _vervang_rol(medewerker.id, tenant_id, "admin")
        # De aanvrager telt niet mee als tenantbeheerder (een platform-superuser, F7) maar blijft
        # actief: een uitgezet account mag sinds "uitgeschakeld is uitgeschakeld" geen verzoek meer doen.
        await _sql("UPDATE users SET is_superuser = true WHERE id = :u", u=beheerder.id)

        with caplog.at_level(logging.WARNING):
            await _erase(
                integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id
            )

        assert any(
            r.levelno == logging.WARNING and "tenant_zonder_beheerder" in r.getMessage()
            for r in caplog.records
        )

    async def test_erasing_a_non_last_administrator_leaves_no_such_line(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _vervang_rol(medewerker.id, tenant_id, "admin")

        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)

        assert "tenant_zonder_beheerder" not in await _auditacties(tenant_id)

    async def test_the_audit_line_carries_no_personal_data(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving

        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)

        rijen = (
            await _sql(
                "SELECT details::text, description FROM audit_logs "
                "WHERE tenant_id = :t AND action = 'gdpr_user_erase_requested'",
                t=tenant_id,
            )
        ).all()
        assert len(rijen) == 1
        assert EMAIL_MEDEWERKER not in " ".join(str(k) for k in rijen[0])

    async def test_requesting_twice_keeps_the_first_term(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)
        eerste = (await _gebruiker(medewerker.id))["gepland"]

        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)

        assert (await _gebruiker(medewerker.id))["gepland"] == eerste


@pytest.mark.asyncio
@pytest.mark.integration
class TestDePurgeControleertOpUitvoeren:
    async def test_a_purge_for_a_user_whose_term_has_not_expired_is_skipped(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """De aanvraag kan tussen inplannen en uitvoeren zijn ingetrokken of niet vervallen zijn."""
        from src.core.actors.gdpr_purge import _run_purge_en_controleer

        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)

        resultaat = await _run_purge_en_controleer(
            medewerker.id, tenant_id, "all", alleen_indien_vervallen=True
        )

        assert "overgeslagen" in resultaat
        assert await _tel(medewerker, "cva_conversations") == 1

    async def test_a_purge_for_a_user_without_a_planned_erasure_is_skipped(
        self, omgeving: Any
    ) -> None:
        from src.core.actors.gdpr_purge import _run_purge_en_controleer

        tenant_id, _, medewerker, _, _ = omgeving

        resultaat = await _run_purge_en_controleer(
            medewerker.id, tenant_id, "all", alleen_indien_vervallen=True
        )

        assert "overgeslagen" in resultaat
        assert await _tel(medewerker, "cva_conversations") == 1


async def _zet_workflow(tenant_id: int, wf_id: str) -> None:
    await _sql("DELETE FROM c7_workflows WHERE id = :i", i=wf_id)
    await _sql(
        "INSERT INTO c7_workflows (id, name, workflow_type, trigger_type, nodes, edges, "
        "tenant_id, is_active) VALUES (:i, 'avg30', 'linear', 'manual', '[]', '[]', :t, true)",
        i=wf_id,
        t=tenant_id,
    )


async def _workflow_actief(wf_id: str) -> bool:
    return bool(
        (await _sql("SELECT is_active FROM c7_workflows WHERE id = :i", i=wf_id)).scalar_one()
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestUitDeReviewGaten:
    async def test_a_new_delete_all_after_an_expired_term_gets_a_fresh_30_days(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """Een verstreken termijn mag niet worden overgenomen: dan viel de wachttijd weg."""
        tenant_id, beheerder, _, _, _ = omgeving
        await _delete_all(integration_app, tenant_id, beheerder)
        await _sql(
            "UPDATE audit_logs SET details = (details::jsonb || jsonb_build_object("
            "'scheduled_purge', to_char(now() - interval '1 day', "
            "'YYYY-MM-DD\"T\"HH24:MI:SS.US\"+00:00\"')))::json "
            "WHERE tenant_id = :t AND action = 'gdpr_delete_all'",
            t=tenant_id,
        )

        antwoord = await _delete_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 200, antwoord.text
        gepland = datetime.fromisoformat(antwoord.json()["scheduled_purge_date"])
        assert gepland - datetime.now(timezone.utc) > timedelta(days=DAGEN - 1)

    async def test_a_failed_substep_is_retried_and_then_wipes(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        """De termijn mag pas worden gewist als de purge VOLLEDIG slaagde; anders doet de retry niets."""
        from unittest.mock import AsyncMock

        from src.core.actors.gdpr_purge import PurgeDeelstappenMislukt, _run_purge_en_controleer

        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)
        await _laat_de_termijn_verstrijken(tenant_id)

        with patch(
            "src.core.actors.gdpr_purge._wis_memory_items",
            new=AsyncMock(side_effect=RuntimeError("stuk")),
        ):
            with pytest.raises(PurgeDeelstappenMislukt):
                await _run_purge_en_controleer(
                    medewerker.id, tenant_id, "all", alleen_indien_vervallen=True
                )
        await _run_purge_en_controleer(
            medewerker.id, tenant_id, "all", alleen_indien_vervallen=True
        )

        assert await _tel(medewerker, "memory_items") == 0

    async def test_the_planner_picks_up_a_user_whose_purge_failed(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        from unittest.mock import AsyncMock

        from src.core.actors.gdpr_purge import PurgeDeelstappenMislukt, _run_purge_en_controleer

        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)
        await _laat_de_termijn_verstrijken(tenant_id)
        with patch(
            "src.core.actors.gdpr_purge._wis_memory_items",
            new=AsyncMock(side_effect=RuntimeError("stuk")),
        ):
            with pytest.raises(PurgeDeelstappenMislukt):
                await _run_purge_en_controleer(
                    medewerker.id, tenant_id, "all", alleen_indien_vervallen=True
                )

        assert await _draai_planner_en_purges() == [(medewerker.id, tenant_id)]

    async def test_the_requesting_administrator_stays_active_to_be_able_to_revoke(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving

        await _delete_all(integration_app, tenant_id, beheerder)

        assert [(await _gebruiker(p.id))["actief"] for p in (beheerder, medewerker)] == [True, False]

    async def test_the_tenant_stays_active_during_the_term(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        await _delete_all(integration_app, tenant_id, beheerder)

        actief = (await _sql("SELECT is_active FROM tenants WHERE id = :t", t=tenant_id)).scalar_one()
        assert actief is True

    async def test_a_loose_erasure_is_not_reverted_by_revoking_delete_all(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, collega, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), collega.id)
        await _delete_all(integration_app, tenant_id, beheerder)

        await _revoke_all(integration_app, tenant_id, beheerder)

        assert [(await _gebruiker(p.id))["actief"] for p in (medewerker, collega)] == [True, False]

    async def test_revoking_delete_all_without_a_delete_all_is_refused(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)

        antwoord = await _revoke_all(integration_app, tenant_id, beheerder)

        assert antwoord.status_code == 409

    async def test_workflows_switched_off_by_delete_all_come_back_after_revoking(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        await _zet_workflow(tenant_id, "avg30-wf-1")
        try:
            await _delete_all(integration_app, tenant_id, beheerder)
            uitgezet = not await _workflow_actief("avg30-wf-1")

            await _revoke_all(integration_app, tenant_id, beheerder)

            assert (uitgezet, await _workflow_actief("avg30-wf-1")) == (True, True)
        finally:
            await _sql("DELETE FROM c7_workflows WHERE id = 'avg30-wf-1'")

    async def test_a_second_delete_all_does_not_lose_the_workflows_to_restore(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, _, _, _ = omgeving
        await _zet_workflow(tenant_id, "avg30-wf-2")
        try:
            await _delete_all(integration_app, tenant_id, beheerder)
            await _delete_all(integration_app, tenant_id, beheerder)

            await _revoke_all(integration_app, tenant_id, beheerder)

            assert await _workflow_actief("avg30-wf-2") is True
        finally:
            await _sql("DELETE FROM c7_workflows WHERE id = 'avg30-wf-2'")

    async def test_erasing_yourself_is_refused(self, omgeving: Any, integration_app: Any) -> None:
        tenant_id, beheerder, _, _, _ = omgeving

        antwoord = await _erase(
            integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), beheerder.id
        )

        assert antwoord.status_code == 409

    async def test_a_user_who_was_already_purged_is_refused(
        self, omgeving: Any, integration_app: Any
    ) -> None:
        tenant_id, beheerder, medewerker, _, _ = omgeving
        await _erase(integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id)
        await _laat_de_termijn_verstrijken(tenant_id)
        await _draai_planner_en_purges()

        antwoord = await _erase(
            integration_app, tenant_id, (beheerder.id, EMAIL_BEHEERDER), medewerker.id
        )

        assert antwoord.status_code == 409
