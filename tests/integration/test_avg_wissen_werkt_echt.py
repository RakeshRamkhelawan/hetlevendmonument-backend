"""De AVG-purge van een medewerker wist of anonimiseert echt alles van die persoon (AVG art. 17).

De levende route is `POST /api/gdpr/delete-all` (beheerder); die plant de purge-actor in
(`src/core/actors/gdpr_purge.py`). `DSARService.delete_user_data` heeft geen aanroeper en telt hier
niet mee (besluit regie 2026-10-11). Gemeten tegen echte Postgres, met wegwerpgebruikers in tenant 1
(het doel en een collega) en in tenant 2 (controlegroep):

1. Na de purge: de gebruikersrij is geanonimiseerd, zijn inlog is onbruikbaar, en zijn gesprekken
   (`conversations`, `cva_conversations`), geheugen (`memory_items`), AI-besluiten, taken, punten en
   profileringskeuzes zijn weg.
2. De gegevens van de collega en van de andere tenant blijven staan.
3. Een deelstap die faalt stopt de purge niet en staat in het antwoord (`mislukte_deelstappen`) en
   in een WARNING; zij wordt niet stil geslikt.

`cva_conversations.user_id` is TEKST; vergelijken met een getal gaf "operator does not exist:
character varying = integer" (gemeten 2026-10-11).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import _sql
from tests.integration.test_laatste_beheerder import _aanroep

TENANT = 1
ANDERE_TENANT = 2
EMAIL_DOEL = "avg-wissen-doel@avg-wissen.invalid"
EMAIL_COLLEGA = "avg-wissen-collega@avg-wissen.invalid"
EMAIL_ANDERE_TENANT = "avg-wissen-t2@avg-wissen.invalid"
GEHEIM = "geheim-gesprek-inhoud"

#: tabel -> (kolom met de gebruiker, is die kolom tekst?)
PERSOONSTABELLEN = {
    "cva_conversations": ("user_id", True),
    "memory_items": ("user_id", False),
    "ai_decisions": ("user_id", True),
    "agentic_tasks": ("created_by", False),
    "point_transactions": ("user_id", False),
    "user_points": ("user_id", False),
    "user_profiling_opt_outs": ("user_id", True),
}


@dataclass
class Persoon:
    id: int
    tenant_id: int


async def _maak_gebruiker(email: str, tenant_id: int) -> Persoon:
    for oud in (await _sql("SELECT id FROM users WHERE email = :e", e=email)).all():
        await _ruim_op(int(oud[0]))
    rij = (
        await _sql(
            "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
            "VALUES (:e, 'echt-wachtwoord-hash', true, false, :t) RETURNING id",
            e=email,
            t=tenant_id,
        )
    ).one()
    user_id = int(rij[0])
    await _sql(
        "INSERT INTO user_roles (user_id, role_id, tenant_id) "
        "SELECT :u, id, :t FROM roles WHERE tenant_id = :t ORDER BY id LIMIT 1",
        u=user_id,
        t=tenant_id,
    )
    return Persoon(user_id, tenant_id)


async def _vul(p: Persoon) -> None:
    """Geef de persoon een rij in elke tabel met persoonsgegevens."""
    uid, tid = p.id, p.tenant_id
    await _sql(
        "INSERT INTO cva_conversations (id, session_id, user_id, tenant_id, user_message, "
        "cva_response, conversation_turn) VALUES (:i, 's', :u, :t, :m, :m, 1)",
        i=f"conv_avg_{uid}",
        u=str(uid),
        t=tid,
        m=GEHEIM,
    )
    gesprek = (
        await _sql(
            "INSERT INTO conversations (title, tenant_id, user_id) VALUES (:m, :t, :u) RETURNING id",
            m=GEHEIM,
            t=tid,
            u=uid,
        )
    ).one()
    await _sql(
        "INSERT INTO conversation_messages (conversation_id, tenant_id, role, content) "
        "VALUES (:c, :t, 'user', :m)",
        c=int(gesprek[0]),
        t=tid,
        m=GEHEIM,
    )
    await _sql(
        "INSERT INTO memory_items (tenant_id, user_id, memory_type, content, confidence, "
        "importance, source_type, privacy_scope, status, tags, entities, provenance) "
        "VALUES (:t, :u, 'fact', :m, 0.5, 0.5, 'chat', 'user', 'active', '[]', '[]', '{}')",
        t=tid,
        u=uid,
        m=GEHEIM,
    )
    await _sql(
        "INSERT INTO ai_decisions (user_id, tenant_id, agent_id, decision_type, explanation, "
        "profiling_involved, human_review_available, human_review_requested) "
        "VALUES (:u, :t, 'a', 'x', :m, false, false, false)",
        u=str(uid),
        t=tid,
        m=GEHEIM,
    )
    await _sql(
        "INSERT INTO agentic_tasks (id, tenant_id, title, created_by) "
        "VALUES (gen_random_uuid(), :t, :m, :u)",
        t=tid,
        m=GEHEIM,
        u=uid,
    )
    await _sql(
        "INSERT INTO point_transactions (user_id, tenant_id, points, action) "
        "VALUES (:u, :t, 5, 'x')",
        u=uid,
        t=tid,
    )
    await _sql(
        "INSERT INTO user_points (user_id, tenant_id, total_points, level, current_streak, "
        "longest_streak) VALUES (:u, :t, 5, 1, 0, 0)",
        u=uid,
        t=tid,
    )
    await _sql(
        "INSERT INTO user_profiling_opt_outs (user_id, tenant_id, profiling_type, opted_out) "
        "VALUES (:u, :t, 'x', true)",
        u=str(uid),
        t=tid,
    )


async def _tel(p: Persoon, tabel: str) -> int:
    kolom, tekst = PERSOONSTABELLEN[tabel]
    waarde: Any = str(p.id) if tekst else p.id
    return int(
        (
            await _sql(
                f"SELECT count(*) FROM {tabel} WHERE {kolom} = :u AND tenant_id = :t",  # noqa: S608
                u=waarde,
                t=p.tenant_id,
            )
        ).scalar_one()
    )


async def _ruim_op(user_id: int) -> None:
    sid = str(user_id)
    await _sql("DELETE FROM cva_conversations WHERE user_id = :s", s=sid)
    await _sql(
        "DELETE FROM conversation_messages WHERE conversation_id IN "
        "(SELECT id FROM conversations WHERE user_id = :u)",
        u=user_id,
    )
    await _sql("DELETE FROM conversations WHERE user_id = :u", u=user_id)
    await _sql("DELETE FROM memory_items WHERE user_id = :u", u=user_id)
    await _sql("DELETE FROM ai_decisions WHERE user_id = :s", s=sid)
    await _sql("DELETE FROM agentic_tasks WHERE created_by = :u", u=user_id)
    await _sql("DELETE FROM point_transactions WHERE user_id = :u", u=user_id)
    await _sql("DELETE FROM user_points WHERE user_id = :u", u=user_id)
    await _sql("DELETE FROM user_profiling_opt_outs WHERE user_id = :s", s=sid)
    await _sql("DELETE FROM audit_logs WHERE user_id = :u", u=user_id)
    await _sql("DELETE FROM user_roles WHERE user_id = :u", u=user_id)
    await _sql("DELETE FROM users WHERE id = :u", u=user_id)


@pytest_asyncio.fixture
async def personen() -> AsyncGenerator[tuple[Persoon, Persoon, Persoon], None]:
    """Het doel, een collega in dezelfde tenant en een gebruiker in een andere tenant."""
    doel = await _maak_gebruiker(EMAIL_DOEL, TENANT)
    collega = await _maak_gebruiker(EMAIL_COLLEGA, TENANT)
    vreemd = await _maak_gebruiker(EMAIL_ANDERE_TENANT, ANDERE_TENANT)
    for p in (doel, collega, vreemd):
        await _vul(p)
    yield doel, collega, vreemd
    for p in (doel, collega, vreemd):
        await _ruim_op(p.id)


async def _purge(p: Persoon, scope: str = "all") -> dict[str, Any]:
    from src.core.actors.gdpr_purge import _run_purge

    return await _run_purge(p.id, p.tenant_id, scope)


@pytest.mark.asyncio
@pytest.mark.integration
class TestDePurgeWistEchtAlles:
    async def test_the_user_row_is_anonymised(
        self, personen: tuple[Persoon, Persoon, Persoon]
    ) -> None:
        doel, _, _ = personen

        await _purge(doel)

        rij = (await _sql("SELECT email, is_active FROM users WHERE id = :u", u=doel.id)).one()
        assert (rij[0], rij[1]) == (f"purged_{doel.id}@purged.invalid", False)

    async def test_the_login_is_unusable(self, personen: tuple[Persoon, Persoon, Persoon]) -> None:
        doel, _, _ = personen

        await _purge(doel)

        wachtwoord = (
            await _sql("SELECT hashed_password FROM users WHERE id = :u", u=doel.id)
        ).scalar_one()
        assert wachtwoord == "[PURGED]"

    @pytest.mark.parametrize("tabel", sorted(PERSOONSTABELLEN))
    async def test_the_persons_rows_are_gone(
        self, personen: tuple[Persoon, Persoon, Persoon], tabel: str
    ) -> None:
        doel, _, _ = personen

        await _purge(doel)

        assert await _tel(doel, tabel) == 0

    async def test_the_conversation_texts_are_anonymised(
        self, personen: tuple[Persoon, Persoon, Persoon]
    ) -> None:
        doel, _, _ = personen

        await _purge(doel)

        rest = (
            await _sql(
                "SELECT count(*) FROM conversation_messages m JOIN conversations c "
                "ON c.id = m.conversation_id WHERE c.user_id = :u AND m.content = :m",
                u=doel.id,
                m=GEHEIM,
            )
        ).scalar_one()
        assert rest == 0

    @pytest.mark.parametrize("tabel", sorted(PERSOONSTABELLEN))
    async def test_a_colleague_in_the_same_tenant_keeps_the_rows(
        self, personen: tuple[Persoon, Persoon, Persoon], tabel: str
    ) -> None:
        doel, collega, _ = personen

        await _purge(doel)

        assert await _tel(collega, tabel) == 1

    @pytest.mark.parametrize("tabel", sorted(PERSOONSTABELLEN))
    async def test_a_user_of_another_tenant_keeps_the_rows(
        self, personen: tuple[Persoon, Persoon, Persoon], tabel: str
    ) -> None:
        doel, _, vreemd = personen

        await _purge(doel)

        assert await _tel(vreemd, tabel) == 1

    async def test_the_colleagues_account_is_untouched(
        self, personen: tuple[Persoon, Persoon, Persoon]
    ) -> None:
        doel, collega, _ = personen

        await _purge(doel)

        rij = (await _sql("SELECT email, is_active FROM users WHERE id = :u", u=collega.id)).one()
        assert (rij[0], rij[1]) == (EMAIL_COLLEGA, True)

    async def test_a_messages_only_purge_leaves_the_other_categories(
        self, personen: tuple[Persoon, Persoon, Persoon]
    ) -> None:
        doel, _, _ = personen

        await _purge(doel, scope="messages")

        assert await _tel(doel, "memory_items") == 1

    async def test_a_successful_purge_reports_no_failed_substeps(
        self, personen: tuple[Persoon, Persoon, Persoon]
    ) -> None:
        doel, _, _ = personen

        resultaat = await _purge(doel)

        assert resultaat["mislukte_deelstappen"] == []


@pytest.mark.asyncio
@pytest.mark.integration
class TestEenMislukteDeelstapIsZichtbaar:
    async def test_a_failing_substep_is_named_in_the_result(
        self, personen: tuple[Persoon, Persoon, Persoon]
    ) -> None:
        doel, _, _ = personen

        with patch(
            "src.core.actors.gdpr_purge._wis_memory_items",
            new=AsyncMock(side_effect=RuntimeError("stuk")),
        ):
            resultaat = await _purge(doel)

        assert resultaat["mislukte_deelstappen"] == ["memory_items"]

    async def test_a_failing_substep_does_not_stop_the_other_substeps(
        self, personen: tuple[Persoon, Persoon, Persoon]
    ) -> None:
        doel, _, _ = personen

        with patch(
            "src.core.actors.gdpr_purge._wis_memory_items",
            new=AsyncMock(side_effect=RuntimeError("stuk")),
        ):
            await _purge(doel)

        assert await _tel(doel, "cva_conversations") == 0

    async def test_a_failing_substep_leaves_a_warning(
        self,
        personen: tuple[Persoon, Persoon, Persoon],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        doel, _, _ = personen

        with caplog.at_level(logging.WARNING):
            with patch(
                "src.core.actors.gdpr_purge._wis_memory_items",
                new=AsyncMock(side_effect=RuntimeError("stuk")),
            ):
                await _purge(doel)

        assert any(
            r.levelno >= logging.WARNING and "memory_items" in r.getMessage()
            for r in caplog.records
        )

    async def test_a_failing_substep_is_in_the_audit_line(
        self, personen: tuple[Persoon, Persoon, Persoon]
    ) -> None:
        doel, _, _ = personen

        with patch(
            "src.core.actors.gdpr_purge._wis_memory_items",
            new=AsyncMock(side_effect=RuntimeError("stuk")),
        ):
            await _purge(doel)

        details = (
            await _sql(
                "SELECT details FROM audit_logs WHERE tenant_id = :t AND action = "
                "'gdpr_purge_executed' AND user_id = :u ORDER BY id DESC LIMIT 1",
                t=doel.tenant_id,
                u=doel.id,
            )
        ).scalar_one()
        assert details["mislukte_deelstappen"] == ["memory_items"]

    async def test_the_audit_description_of_a_partial_purge_says_so(
        self, personen: tuple[Persoon, Persoon, Persoon]
    ) -> None:
        """Bij een retry staan er meerdere regels; alleen de echt geslaagde mag 'completed' zeggen."""
        doel, _, _ = personen

        with patch(
            "src.core.actors.gdpr_purge._wis_memory_items",
            new=AsyncMock(side_effect=RuntimeError("stuk")),
        ):
            await _purge(doel)

        beschrijving = (
            await _sql(
                "SELECT description FROM audit_logs WHERE tenant_id = :t AND action = "
                "'gdpr_purge_executed' AND user_id = :u ORDER BY id DESC LIMIT 1",
                t=doel.tenant_id,
                u=doel.id,
            )
        ).scalar_one()
        assert "memory_items" in beschrijving and "completed" not in beschrijving


@pytest_asyncio.fixture
async def eigen_tenant() -> AsyncGenerator[tuple[int, Persoon, Persoon], None]:
    """Een verse tenant met een beheerder en een medewerker; het wissen raakt alleen deze tenant."""
    await _sql("DELETE FROM tenants WHERE slug = 'avg-wissen-tenant'")
    tenant_id = int(
        (
            await _sql(
                "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
                "VALUES ('AVG wissen', 'avg-wissen-tenant', true, 10, 10, 1) RETURNING id"
            )
        ).scalar_one()
    )
    await _sql(
        "INSERT INTO roles (tenant_id, name, is_active) VALUES (:t, 'admin', true)", t=tenant_id
    )
    beheerder = await _maak_gebruiker("avg-wissen-beheerder@avg-wissen.invalid", tenant_id)
    medewerker = await _maak_gebruiker("avg-wissen-medewerker@avg-wissen.invalid", tenant_id)
    yield tenant_id, beheerder, medewerker
    for p in (beheerder, medewerker):
        await _ruim_op(p.id)
    await _sql("DELETE FROM roles WHERE tenant_id = :t", t=tenant_id)
    await _sql("DELETE FROM audit_logs WHERE tenant_id = :t", t=tenant_id)
    await _sql("DELETE FROM tenants WHERE id = :t", t=tenant_id)


@pytest.mark.asyncio
@pytest.mark.integration
class TestDeleteAllPlantEenPurgePerMedewerker:
    async def test_a_soft_delete_all_plans_the_erasure_of_every_user_of_the_tenant(
        self, eigen_tenant: tuple[int, Persoon, Persoon], integration_app: Any
    ) -> None:
        """delete-all is tenantbreed: ook de medewerker staat gepland, niet alleen de beheerder.

        Sinds 2026-10-12 (besluit Rakesh) wordt er niets direct gepurged: elke gebruiker krijgt
        `deletion_scheduled_for`; de planner (avg_purge_job) doet de rest na 30 dagen.
        """
        from tests.integration.conftest import _build_test_token

        tenant_id, beheerder, medewerker = eigen_tenant
        token = _build_test_token(
            user_id=beheerder.id,
            email="avg-wissen-beheerder@avg-wissen.invalid",
            tenant_id=tenant_id,
        )
        antwoord = await _aanroep(
            integration_app,
            token,
            "POST",
            "/api/gdpr/delete-all",
            {"delete_type": "soft", "confirmation_code": str(tenant_id)},
        )

        assert antwoord.status_code == 200, antwoord.text
        gepland = (
            await _sql(
                "SELECT id FROM users WHERE tenant_id = :t AND deletion_scheduled_for IS NOT NULL",
                t=tenant_id,
            )
        ).all()
        assert sorted(int(r[0]) for r in gepland) == sorted([beheerder.id, medewerker.id])

    async def test_the_answer_carries_the_tenant_as_text(
        self, eigen_tenant: tuple[int, Persoon, Persoon], integration_app: Any
    ) -> None:
        from tests.integration.conftest import _build_test_token

        tenant_id, beheerder, _ = eigen_tenant
        token = _build_test_token(
            user_id=beheerder.id,
            email="avg-wissen-beheerder@avg-wissen.invalid",
            tenant_id=tenant_id,
        )
        with patch(
            "src.core.api.v1.gdpr_compliance.erasure_router._schedule_purge_task", lambda **_: None
        ):
            antwoord = await _aanroep(
                integration_app,
                token,
                "POST",
                "/api/gdpr/delete-all",
                {"delete_type": "soft", "confirmation_code": str(tenant_id)},
            )

        assert antwoord.json()["tenant_id"] == str(tenant_id)

    async def test_a_wrong_confirmation_code_is_refused(
        self, eigen_tenant: tuple[int, Persoon, Persoon], integration_app: Any
    ) -> None:
        from tests.integration.conftest import _build_test_token

        tenant_id, beheerder, _ = eigen_tenant
        token = _build_test_token(
            user_id=beheerder.id,
            email="avg-wissen-beheerder@avg-wissen.invalid",
            tenant_id=tenant_id,
        )

        antwoord = await _aanroep(
            integration_app,
            token,
            "POST",
            "/api/gdpr/delete-all",
            {"delete_type": "soft", "confirmation_code": "999999"},
        )

        assert antwoord.status_code == 400

    async def test_a_hard_delete_all_removes_the_users_and_the_tenant(
        self, eigen_tenant: tuple[int, Persoon, Persoon], integration_app: Any
    ) -> None:
        from tests.integration.conftest import _build_test_token

        tenant_id, beheerder, medewerker = eigen_tenant
        token = _build_test_token(
            user_id=beheerder.id,
            email="avg-wissen-beheerder@avg-wissen.invalid",
            tenant_id=tenant_id,
        )

        export = await _aanroep(
            integration_app,
            token,
            "POST",
            "/api/gdpr/delete-all/export",
            {"recipient": "klant"},
        )
        assert export.status_code == 200, export.text
        antwoord = await _aanroep(
            integration_app,
            token,
            "POST",
            "/api/gdpr/delete-all",
            {"delete_type": "hard", "confirmation_code": str(tenant_id)},
        )

        assert antwoord.status_code == 200, antwoord.text
        resterend = {
            "users": (await _sql("SELECT count(*) FROM users WHERE tenant_id = :t", t=tenant_id)),
            "tenants": (await _sql("SELECT count(*) FROM tenants WHERE id = :t", t=tenant_id)),
            "user_roles": (
                await _sql("SELECT count(*) FROM user_roles WHERE tenant_id = :t", t=tenant_id)
            ),
        }
        assert {k: v.scalar_one() for k, v in resterend.items()} == {
            "users": 0,
            "tenants": 0,
            "user_roles": 0,
        }

    async def test_a_hard_delete_all_leaves_no_orphaned_personal_rows(
        self, eigen_tenant: tuple[int, Persoon, Persoon], integration_app: Any
    ) -> None:
        """ai_decisions en user_profiling_opt_outs hebben GEEN vreemde sleutel naar de tenant."""
        from tests.integration.conftest import _build_test_token

        tenant_id, beheerder, medewerker = eigen_tenant
        await _vul(medewerker)
        token = _build_test_token(
            user_id=beheerder.id,
            email="avg-wissen-beheerder@avg-wissen.invalid",
            tenant_id=tenant_id,
        )

        export = await _aanroep(
            integration_app,
            token,
            "POST",
            "/api/gdpr/delete-all/export",
            {"recipient": "klant"},
        )
        assert export.status_code == 200, export.text
        await _aanroep(
            integration_app,
            token,
            "POST",
            "/api/gdpr/delete-all",
            {"delete_type": "hard", "confirmation_code": str(tenant_id)},
        )

        wezen = [
            (await _sql(f"SELECT count(*) FROM {tabel} WHERE tenant_id = :t", t=tenant_id)).scalar_one()  # noqa: S608
            for tabel in ("ai_decisions", "user_profiling_opt_outs")
        ]
        assert wezen == [0, 0]


@pytest.mark.asyncio
class TestEenMislukteDeelstapLaatDeActorOpnieuwProberen:
    async def test_the_actor_raises_when_a_substep_failed(self) -> None:
        """Dramatiq probeert opnieuw bij een exceptie; de purge is idempotent, dus dat is veilig."""
        from src.core.actors.gdpr_purge import PurgeDeelstappenMislukt, _run_purge_en_controleer

        mislukt = {"mislukte_deelstappen": ["memory_items"]}
        with patch("src.core.actors.gdpr_purge._run_purge", new=AsyncMock(return_value=mislukt)):
            with pytest.raises(PurgeDeelstappenMislukt):
                await _run_purge_en_controleer(1, 1, "all")

    async def test_the_actor_returns_the_result_when_all_substeps_succeeded(self) -> None:
        from src.core.actors.gdpr_purge import _run_purge_en_controleer

        goed = {"mislukte_deelstappen": []}
        with patch("src.core.actors.gdpr_purge._run_purge", new=AsyncMock(return_value=goed)):
            assert await _run_purge_en_controleer(1, 1, "all") == goed
