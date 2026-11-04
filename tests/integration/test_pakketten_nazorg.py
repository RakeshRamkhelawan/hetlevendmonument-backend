"""Pakketten nazorg: geen omweg langs de schakelaar, wie zette het aan (SP-KLANT-04, ADR-039).

Brief: docs/agent-briefs/generated/2026-10-15-sprint-dag-pakketten-nazorg.md.

Echte app-stack, echte Postgres, de echte rolzaaier (zelfde opzet als
`test_pakket_aanzetten_per_klant.py`).

Wat gemeten wordt:

(1) omweg: een agent van een pakket is via de losse agentroutes NIET te starten terwijl het pakket
    uit staat. De Council is hier op de grens goedgekeurd, zodat de test meet wat DAARNA gebeurt:
    de routes zoeken de agent in de `AgentRegistry` en vinden de ALS-pakketskills daar niet. De
    structuurcontrole die bewaakt wie de skills WEL kan instantieren staat in
    `tests/architecture/test_pakketagent_heeft_een_bekende_aanroeper.py`;
(2) wie zette het aan: de lijst en het antwoord van de PUT zeggen wie en wanneer; de auditregel
    houdt de volledige geschiedenis (een regel per wijziging, met de gebruiker);
(3) een falende auditregel breekt het aanzetten niet en wordt gelogd.

Wat NIET gemeten is: een draaiende applicatie met scherm; een echte LLM-uitvoering.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_packs_execute_route import (  # noqa: F401
    PACK,
    TENANT,
    _client,
    _gebruiker_met_rol,
    beheerder,
    medewerker,
    standaardrollen,
)
from tests.integration.test_pakket_aanzetten_per_klant import (
    ACTIVATIES,
    EVENT,
    _put,
)

BEHEERDER_EMAIL = "admin@integration.test"


# ---------------------------------------------------------------------------
# (1) geen omweg langs de schakelaar
# ---------------------------------------------------------------------------

AGENTROUTES = (
    "/api/v1/agents/agent/execute/{id}",
    "/api/v1/agents/execute/{id}",
)


@pytest.fixture
def skill_uitvoeringen(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Legt vast als een pakketskill WERKELIJK wordt uitgevoerd, en keurt de Council goed."""
    from src.core.als.agents.skills.dunning import DunningSkill
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill
    from src.core.api.v1.agents import agent_execution_router

    gezien: list[str] = []

    def _opname(naam: str) -> Any:
        async def _uitvoeren(self: Any, *args: Any, **kwargs: Any) -> Any:
            gezien.append(naam)
            raise AssertionError(f"{naam} is uitgevoerd zonder dat het pakket aan staat")

        return _uitvoeren

    monkeypatch.setattr(DunningSkill, "execute_with_manifest_prompt", _opname("dunning"))
    monkeypatch.setattr(
        SkillsGapTrainingSkill, "execute_with_manifest_prompt", _opname("skillsgaptraining")
    )

    async def _goedgekeurd(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(agent_execution_router, "require_agent_council_approval", _goedgekeurd)
    return gezien


@pytest.mark.integration
@pytest.mark.asyncio
class TestGeenOmwegLangsDeSchakelaar:
    @pytest.mark.parametrize("agent_id", ["skillsgaptraining", "dunning"])
    async def test_een_pakketagent_is_niet_te_starten_via_een_pad_met_de_agent_in_de_url(
        self, beheerder: AsyncClient, skill_uitvoeringen: list[str], agent_id: str
    ) -> None:
        for route in AGENTROUTES:
            antwoord = await beheerder.post(route.format(id=agent_id), json={"input": "hallo"})

            assert antwoord.status_code == 404, f"{route}: {antwoord.status_code} {antwoord.text}"
        assert skill_uitvoeringen == []

    @pytest.mark.parametrize("agent_id", ["skillsgaptraining", "dunning"])
    async def test_een_pakketagent_is_niet_te_starten_via_de_dispatcher_met_de_agent_in_de_body(
        self, beheerder: AsyncClient, skill_uitvoeringen: list[str], agent_id: str
    ) -> None:
        antwoord = await beheerder.post(
            "/api/v1/agents/execute", json={"agent_id": agent_id, "query": "hallo"}
        )

        assert antwoord.status_code == 404, antwoord.text
        assert skill_uitvoeringen == []


# ---------------------------------------------------------------------------
# (2) wie zette het aan, en de volledige geschiedenis
# ---------------------------------------------------------------------------


async def _audit_regels(sessie: AsyncSession) -> list[tuple[int | None, dict[str, Any]]]:
    rijen = await sessie.execute(
        text(
            "SELECT user_id, event_metadata FROM audit_logs "
            "WHERE tenant_id = :t AND event_type = :e ORDER BY id"
        ),
        {"t": TENANT, "e": EVENT},
    )
    return [(r.user_id, r.event_metadata) for r in rijen]


def _stand(lijst: dict[str, Any], pack_id: str = PACK) -> dict[str, Any]:
    (rij,) = [p for p in lijst["data"] if p["pack_id"] == pack_id]
    return rij


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieZetAan:
    async def test_het_antwoord_van_de_put_zegt_wie_en_wanneer(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        antwoord = await beheerder.put(_put(), json={"is_enabled": True})

        data = antwoord.json()["data"]
        assert data["last_changed_by"] == BEHEERDER_EMAIL, antwoord.text
        assert datetime.fromisoformat(data["last_changed_at"]).tzinfo is not None

    async def test_de_lijst_zegt_wie_en_wanneer_voor_een_aangezet_pakket(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        await beheerder.put(_put(), json={"is_enabled": True})

        lijst = await beheerder.get(ACTIVATIES)

        rij = _stand(lijst.json())
        assert rij["last_changed_by"] == BEHEERDER_EMAIL, lijst.text
        assert rij["last_changed_at"] is not None

    async def test_een_medewerker_krijgt_geen_wijziger_en_geen_adres(
        self,
        beheerder: AsyncClient,
        medewerker: AsyncClient,
        standaardrollen: AsyncSession,
    ) -> None:
        """AVG-dataminimalisatie: de medewerker heeft het adres van de beheerder niet nodig."""
        await beheerder.put(_put(), json={"is_enabled": True})

        lijst = await medewerker.get(ACTIVATIES)

        assert lijst.status_code == 200, lijst.text
        rij = _stand(lijst.json())
        assert rij["is_enabled"] is True
        assert "last_changed_by" not in rij and "last_changed_at" not in rij, rij
        assert BEHEERDER_EMAIL not in lijst.text

    async def test_een_pakket_dat_nooit_is_aangeraakt_heeft_geen_wijziging(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        lijst = await beheerder.get(ACTIVATIES)

        rij = _stand(lijst.json(), "hr.reskilling_engine")
        assert (rij["last_changed_by"], rij["last_changed_at"]) == (None, None), lijst.text

    async def test_de_lijst_toont_de_laatste_wijziger_en_de_audit_houdt_beide(
        self,
        integration_app: Any,
        beheerder: AsyncClient,
        standaardrollen: AsyncSession,
    ) -> None:
        tweede_id = await _gebruiker_met_rol(standaardrollen, "admin", "admin2@integration.test")
        await standaardrollen.commit()
        await beheerder.put(_put(), json={"is_enabled": True})
        lijst: dict[str, Any] = {}
        async for tweede in _client(
            integration_app,
            standaardrollen,
            user_id=tweede_id,
            email="admin2@integration.test",
            rollen=["admin"],
            csrf=False,
        ):
            await tweede.put(_put(), json={"is_enabled": False})
            lijst = (await tweede.get(ACTIVATIES)).json()

        assert _stand(lijst)["last_changed_by"] == "admin2@integration.test"
        regels = await _audit_regels(standaardrollen)
        assert [(gebruiker, meta["is_enabled"]) for gebruiker, meta in regels] == [
            (1, True),
            (tweede_id, False),
        ]

    async def test_de_lijst_lekt_geen_adres_van_een_gebruiker_van_een_andere_klant(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        """Een rij van klant 1 die naar een gebruiker van klant 2 verwijst, geeft geen adres terug."""
        vreemde = (
            await standaardrollen.execute(
                text(
                    "INSERT INTO users (email, hashed_password, tenant_id, is_active, is_superuser) "
                    "VALUES ('vreemd@andere-klant.test', 'x', 2, true, false) RETURNING id"
                )
            )
        ).scalar_one()
        await standaardrollen.execute(
            text(
                "INSERT INTO tenant_pack_activations (tenant_id, pack_id, is_enabled, "
                "enabled_by_user_id) VALUES (:t, :p, true, :u)"
            ),
            {"t": TENANT, "p": PACK, "u": vreemde},
        )
        await standaardrollen.commit()

        lijst = await beheerder.get(ACTIVATIES)

        rij = _stand(lijst.json())
        assert (rij["is_enabled"], rij["last_changed_by"]) == (True, None), lijst.text
        assert "vreemd@andere-klant.test" not in lijst.text


# ---------------------------------------------------------------------------
# (3) een falende auditregel
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
class TestFalendeAuditregel:
    async def test_aanzetten_slaagt_ook_als_de_auditregel_faalt(
        self,
        beheerder: AsyncClient,
        standaardrollen: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from src.core.governance.services.audit_service import AuditService

        async def _stuk(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("auditlog onbereikbaar")

        monkeypatch.setattr(AuditService, "log_event", _stuk)

        antwoord = await beheerder.put(_put(), json={"is_enabled": True})

        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["data"]["is_enabled"] is True
        aan = (
            await standaardrollen.execute(
                text(
                    "SELECT is_enabled FROM tenant_pack_activations "
                    "WHERE tenant_id = :t AND pack_id = :p"
                ),
                {"t": TENANT, "p": PACK},
            )
        ).scalar_one()
        assert aan is True

    async def test_een_falende_auditregel_wordt_gelogd_met_de_oorzaak(
        self,
        beheerder: AsyncClient,
        standaardrollen: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from src.core.governance.services.audit_service import AuditService

        async def _stuk(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("auditlog onbereikbaar")

        monkeypatch.setattr(AuditService, "log_event", _stuk)

        with caplog.at_level(logging.ERROR, logger="src.core.utils.best_effort"):
            await beheerder.put(_put(), json={"is_enabled": True})

        fouten = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any(
            f"{EVENT} audit log failed" in m and "auditlog onbereikbaar" in m for m in fouten
        ), fouten
        assert await _audit_regels(standaardrollen) == []
