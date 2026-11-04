"""Agentstap dag 1: de GEKOZEN agent draait, met alleen de rechten van de starter (brief 2026-10-24, Keten G).

Gemeten 2026-10-23 (vooraf): een agentstap kon geen enkele agent starten ("Agent executor_agent_001 not found in
process"); de router negeerde bovendien de keuze van de klant. Deze tests lopen over de ECHTE engine-stap
(`ProductionWorkflowEngine._execute_agent_task`), de echte `ProductionAgentRuntime`, de echte skill uit de ALS-catalogus,
de echte broker en de echte `starter_heeft_toolrecht` met rollen uit de zaaier (`ensure_default_roles`) onder de
applicatierol `sanskritisetu_app` (RLS afgedwongen).

Alleen deze grenzen zijn een dubbel: het taalmodel (een script dat een vaste TOOL_CALL teruggeeft), de Council-ingang
en PranaGuard (`tests/fixtures/agent_governance.py`, goedkeurend: de Council zelf wordt niet gemeten) en het lezen van de
vorderingen uit de database (`execute_receivables_tool`, een lege lijst).

**Mutatiebewijs (2026-10-24), een regel per element, gemeten met kopieen als terugweg:**
- skill zonder `_toolrecht_toets` gezet -> 2 rood (geen recht, andere klant); hook laat alles door -> 2 rood;
- engine geeft de starter niet door -> 8 rood; uitvoerbaar = alles met een skill -> 2 rood; altijd `dunning` -> 3 rood;
- startertoets in `act()` weg -> 4 rood (ook de brief-gegevens-test); eigen leesrecht niet getoetst -> 1 rood;
- ruwe `tool_exception` doorgegeven -> 1 rood; telling zonder leesrecht -> eerst 23 groen (niet gevangen), daarom
  `test_het_aantal_openstaande_vorderingen_...` erbij.
- pakketschakelaar niet getoetst -> 2 rood; `dunning` niet meer vrijgesteld -> 1 rood; pakket van elke klant telt -> 2 rood.
Legitieme kant: alle andere tests blijven groen bij elke mutatie hierboven.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from tests.fixtures.agent_governance import (  # noqa: F401
    council_gate,
    hitl_ticket_repository,
    prana_guard,
)
from tests.integration.security.test_tools_rechten_uit_de_database_onder_de_applicatierol import (  # noqa: F401
    Gebruikers,
    als_applicatierol,
    db,
    gebruikers,
)
from tests.integration.security.test_tools_rechten_uit_de_database_onder_de_applicatierol import (
    pytestmark as _pytestmark,
)

from src.core.workflow.engine import ProductionWorkflowEngine, StapMislukt
from src.core.workflow.providers import ProductionAgentRuntime

pytestmark = _pytestmark

_LEZEN = 'TOOL_CALL: list_receivables {"status": "open"}'
_VERSTUREN = 'TOOL_CALL: send_payment_reminder {"receivable_id": 7, "kind": "herinnering"}'
_VOORBEELD = {
    "success": True,
    "params": {
        "receivable_id": 7,
        "kind": "herinnering",
        "recipient_email": "klant@voorbeeld.example",
        "subject": "Herinnering: factuur F-7",
        "body": "Beste klant, ...",
    },
}


def _engine() -> ProductionWorkflowEngine:
    """De engine-stap zonder de rest van de engine: `_execute_agent_task` gebruikt alleen de runtime."""
    engine = ProductionWorkflowEngine.__new__(ProductionWorkflowEngine)
    engine.agent_runtime = ProductionAgentRuntime()
    return engine


def _stap(agent_id: str) -> Any:
    return {"type": "agent", "agent_id": agent_id, "instruction": "kijk welke facturen openstaan"}


@pytest.fixture
def taalmodel() -> Iterator[AsyncMock]:
    """Het taalmodel is een script: `taalmodel.generate.return_value` bepaalt wat de agent besluit."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=_LEZEN)
    with patch(
        "src.core.als.agents.specialist_base.BaseSpecialistAgent._get_llm_service",
        AsyncMock(return_value=llm),
    ):
        yield llm


@pytest.fixture(autouse=True)
def vorderingen_uit_een_lege_database() -> Iterator[AsyncMock]:
    with patch(
        "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
        "execute_receivables_tool",
        AsyncMock(return_value={"success": True, "receivables": []}),
    ) as dubbel:
        yield dubbel


def _zet_pakket(db: Any, tenant_id: int, pack_id: str, aan: bool) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenant_pack_activations (tenant_id, pack_id, is_enabled) VALUES (%s, %s, %s) "
            "ON CONFLICT (tenant_id, pack_id) DO UPDATE SET is_enabled = EXCLUDED.is_enabled",
            (tenant_id, pack_id, aan),
        )


@pytest.fixture(autouse=True)
def pakketten_staan_aan(db: Any, gebruikers: Gebruikers) -> Iterator[None]:
    """De pakketten van de agents staan voor klant A aan (een beheerder zette ze aan); klant B heeft er geen."""
    for pack_id in ("mkb.zero_admin", "hr.reskilling_engine"):
        _zet_pakket(db, gebruikers.tenant_a, pack_id, True)
    yield


@pytest.fixture
def brief_uit_het_sjabloon() -> Iterator[None]:
    with patch(
        "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry.preview_payment_reminder",
        AsyncMock(return_value=_VOORBEELD),
    ):
        yield


def _verzoek() -> object:
    """Een echt Request-object: de limiet van `/agents/uitvoerbaar` haalt het verzoek uit de argumenten op type."""
    from starlette.requests import Request

    return Request(
        {"type": "http", "method": "GET", "path": "/api/v1/vibe/agents/uitvoerbaar", "headers": [], "query_string": b""}
    )


@pytest.mark.asyncio
class TestDeGekozenAgentDraait:
    async def test_een_editor_start_een_agentstap_en_die_agent_draait(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        uitkomst = await _engine()._execute_agent_task(
            _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=editor
        )

        assert uitkomst["agent_id"] == "dunning"
        assert [r["tool"] for r in uitkomst["output"]["results"]] == ["list_receivables"]

    async def test_de_gekozen_agent_draait_en_geen_andere(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        taalmodel.generate.return_value = "Niets te doen."
        editor = str(gebruikers.per_rol["editor"])
        engine = _engine()

        eerste = await engine._execute_agent_task(
            _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=editor
        )
        tweede = await engine._execute_agent_task(
            _stap("vatcompliance"), {}, tenant_id=gebruikers.tenant_a, starter=editor
        )

        assert (eerste["agent_id"], tweede["agent_id"]) == ("dunning", "vatcompliance")

    async def test_de_instructie_van_de_stap_bereikt_de_agent(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        await _engine()._execute_agent_task(
            _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=editor
        )

        prompt = taalmodel.generate.await_args.args[0][0].content
        assert "kijk welke facturen openstaan" in prompt


@pytest.mark.asyncio
class TestAlleenDeRechtenVanDeStarter:
    async def test_een_gebruiker_zonder_het_recht_voor_de_tool_wordt_geweigerd_met_reden(
        self,
        als_applicatierol: None,
        gebruikers: Gebruikers,
        taalmodel: AsyncMock,
        brief_uit_het_sjabloon: None,
        hitl_ticket_repository: AsyncMock,
    ) -> None:
        from src.core.tool_broker.workflow_identiteit import starter_heeft_toolrecht

        taalmodel.generate.return_value = _VERSTUREN
        gewone_gebruiker = str(gebruikers.per_rol["user"])
        assert not await starter_heeft_toolrecht(
            gewone_gebruiker, "send_payment_reminder", gebruikers.tenant_a
        ), "voorwaarde van de test: rol `user` heeft receivables:propose niet"

        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=gewone_gebruiker
            )

        assert "geen recht" in str(fout.value)
        assert hitl_ticket_repository.create_hitl_request.await_count == 0

    async def test_een_hitl_tool_met_recht_wordt_een_goedkeuringsticket(
        self,
        als_applicatierol: None,
        gebruikers: Gebruikers,
        taalmodel: AsyncMock,
        brief_uit_het_sjabloon: None,
        hitl_ticket_repository: AsyncMock,
    ) -> None:
        from src.core.tool_broker.workflow_identiteit import starter_heeft_toolrecht

        taalmodel.generate.return_value = _VERSTUREN
        beheerder = str(gebruikers.per_rol["admin"])
        assert await starter_heeft_toolrecht(
            beheerder, "send_payment_reminder", gebruikers.tenant_a
        ), "voorwaarde van de test: de beheerder mag een brief klaarzetten"

        with pytest.raises(StapMislukt):
            await _engine()._execute_agent_task(
                _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=beheerder
            )

        kwargs = hitl_ticket_repository.create_hitl_request.await_args.kwargs
        assert (kwargs["action_type"], kwargs["executing_identity"]) == (
            "send_payment_reminder",
            "dunning",
        )

    async def test_een_starter_uit_een_andere_klant_heeft_geen_recht(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        """De klant komt van de uitvoering: een starter van klant A in een uitvoering van klant B krijgt niets."""
        editor_van_a = str(gebruikers.per_rol["editor"])

        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("dunning"), {}, tenant_id=gebruikers.tenant_b, starter=editor_van_a
            )

        assert "geen recht" in str(fout.value)

    async def test_zonder_bekende_starter_start_de_agent_niet(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=None
            )

        assert "geen gebruiker bekend" in str(fout.value)
        assert taalmodel.generate.await_count == 0


@pytest.mark.asyncio
class TestKiesbaarIsUitvoerbaar:
    async def test_een_agent_zonder_workflowuitvoering_geeft_een_nederlandse_reden(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("technicalwriter"), {}, tenant_id=gebruikers.tenant_a, starter=editor
            )

        assert "kan nog niet in een workflow draaien" in str(fout.value)
        assert taalmodel.generate.await_count == 0

    async def test_een_onbekende_agent_geeft_dezelfde_reden(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("executor_agent_001"), {}, tenant_id=gebruikers.tenant_a, starter=editor
            )

        assert "kan nog niet in een workflow draaien" in str(fout.value)

    async def test_de_uitvoerbare_lijst_is_de_bedrade_vijf(self) -> None:
        """Sinds crediteuren dag 2 (merge 9d2fecf4, `src/core/als/enterprise/packs.py`) staat `crediteuren` erbij."""
        from src.core.als.agents.workflow_stap import uitvoerbare_agent_sleutels

        assert uitvoerbare_agent_sleutels() == {
            "skillsgaptraining",
            "dunning",
            "receiptscanner",
            "vatcompliance",
            "crediteuren",
        }

    async def test_de_crediteurenagent_draait_ook_echt_als_stap(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        """Staan op de lijst is niet genoeg: de stap start de skill `crediteuren` en geeft zijn uitkomst terug.

        De pakketcontrole is hier vervangen door `True`. Gemeten 2026-10-28: `crediteuren` zit in GEEN pakket in
        `config/domain_packs.yaml` en staat niet in `EIGEN_KLANTFUNCTIE`, dus zonder deze vervanging weigert de stap met
        'het pakket van deze agent staat voor uw bedrijf niet aan' voor elke klant. Dat is een bevinding voor de
        regie, geen onderdeel van deze test.
        """
        taalmodel.generate.return_value = "Niets te doen."
        editor = str(gebruikers.per_rol["editor"])

        with (
            patch(
                "src.core.als.agents.workflow_stap._pakket_staat_aan", AsyncMock(return_value=True)
            ),
            patch(
                "src.core.auth.rbac.rbac_service.user_has_resource_right",
                AsyncMock(return_value=True),
            ),
        ):
            uitkomst = await _engine()._execute_agent_task(
                _stap("crediteuren"), {}, tenant_id=gebruikers.tenant_a, starter=editor
            )

        assert uitkomst["agent_id"] == "crediteuren"

    async def test_de_crediteurenagent_wordt_getoetst_op_het_schrijfrecht_op_payables(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        with (
            patch(
                "src.core.als.agents.workflow_stap._pakket_staat_aan", AsyncMock(return_value=True)
            ),
            patch(
                "src.core.auth.rbac.rbac_service.user_has_resource_right",
                AsyncMock(return_value=False),
            ) as toets,
        ):
            with pytest.raises(StapMislukt):
                await _engine()._execute_agent_task(
                    _stap("crediteuren"), {}, tenant_id=gebruikers.tenant_a, starter=editor
                )

        assert toets.await_args.args[1:3] == ("payables", "write")


@pytest.mark.asyncio
class TestDeStarterWordtStrengGetoetst:
    @pytest.mark.parametrize("starter", ["abc", "0", "-1", "", " 7", "٣"])
    async def test_een_starter_die_geen_positief_geheel_getal_is_start_de_agent_niet(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock, starter: str
    ) -> None:
        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=starter
            )

        assert "geen gebruiker bekend" in str(fout.value)
        assert taalmodel.generate.await_count == 0

    async def test_zonder_klant_van_de_uitvoering_start_de_agent_niet(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("dunning"), {}, tenant_id=None, starter=editor
            )

        assert "klant van de uitvoering ontbreekt" in str(fout.value)

    async def test_een_toets_die_gooit_is_een_weigering(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])
        kapot = AsyncMock(side_effect=RuntimeError("rechtendatabase weg"))

        with patch("src.core.tool_broker.workflow_identiteit.starter_heeft_toolrecht", kapot):
            with pytest.raises(StapMislukt) as fout:
                await _engine()._execute_agent_task(
                    _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=editor
                )

        assert "niet bereikbaar" in str(fout.value)

    async def test_de_gegevens_van_de_brief_worden_niet_gelezen_zonder_recht(
        self,
        als_applicatierol: None,
        gebruikers: Gebruikers,
        taalmodel: AsyncMock,
        hitl_ticket_repository: AsyncMock,
    ) -> None:
        """Gate 2: `preview_payment_reminder` leest de debiteur; een starter zonder recht ziet daar niets van."""
        taalmodel.generate.return_value = _VERSTUREN
        gewone_gebruiker = str(gebruikers.per_rol["user"])

        with patch(
            "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
            "preview_payment_reminder",
            AsyncMock(return_value=_VOORBEELD),
        ) as voorbeeld:
            with pytest.raises(StapMislukt):
                await _engine()._execute_agent_task(
                    _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=gewone_gebruiker
                )

        assert voorbeeld.await_count == 0

    async def test_een_agent_zonder_tool_wordt_getoetst_op_het_leesrecht_van_de_gegevens(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        """`vatcompliance` leest bonnen rechtstreeks en komt niet langs een tool: dan het leesrecht van de API."""
        editor = str(gebruikers.per_rol["editor"])

        with patch(
            "src.core.auth.rbac.rbac_service.user_has_resource_right", AsyncMock(return_value=False)
        ) as toets:
            with pytest.raises(StapMislukt) as fout:
                await _engine()._execute_agent_task(
                    _stap("vatcompliance"), {}, tenant_id=gebruikers.tenant_a, starter=editor
                )

        assert "geen recht" in str(fout.value)
        assert toets.await_args.args[1:3] == ("receipts", "read")

    async def test_het_aantal_openstaande_vorderingen_wordt_niet_geteld_zonder_leesrecht(
        self,
        als_applicatierol: None,
        gebruikers: Gebruikers,
        taalmodel: AsyncMock,
        vorderingen_uit_een_lege_database: AsyncMock,
    ) -> None:
        """De skill telt na afloop de vorderingen (`_tel_openstaand`); dat is een leesactie van de starter."""
        taalmodel.generate.return_value = "Niets te doen."
        editor = str(gebruikers.per_rol["editor"])

        async def alleen_lezen_niet(starter: str | None, tool: str, tenant: int) -> bool:
            return tool != "list_receivables"

        with patch(
            "src.core.tool_broker.workflow_identiteit.starter_heeft_toolrecht",
            AsyncMock(side_effect=alleen_lezen_niet),
        ):
            uitkomst = await _engine()._execute_agent_task(
                _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=editor
            )

        assert vorderingen_uit_een_lege_database.await_count == 0
        assert uitkomst["output"]["openstaand"] is None

    async def test_een_toolfout_lekt_geen_ruwe_tekst_in_de_uitvoer(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        with patch(
            "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
            "execute_receivables_tool",
            AsyncMock(side_effect=RuntimeError("password=geheim host=intern.example")),
        ):
            with pytest.raises(StapMislukt) as fout:
                await _engine()._execute_agent_task(
                    _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=editor
                )

        assert "geheim" not in str(fout.value) and "mislukt" in str(fout.value)


@pytest.mark.asyncio
class TestDePakketschakelaarGeldtOokInEenWorkflow:
    async def test_een_agent_uit_een_pakket_dat_uit_staat_start_niet(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock, db: Any
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])
        _zet_pakket(db, gebruikers.tenant_a, "mkb.zero_admin", False)

        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("vatcompliance"), {}, tenant_id=gebruikers.tenant_a, starter=editor
            )

        assert "pakket van deze agent staat voor uw bedrijf niet aan" in str(fout.value)

    async def test_de_debiteurenagent_is_een_eigen_klantfunctie_en_start_zonder_pakket(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock, db: Any
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])
        _zet_pakket(db, gebruikers.tenant_a, "mkb.zero_admin", False)

        uitkomst = await _engine()._execute_agent_task(
            _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=editor
        )

        assert uitkomst["agent_id"] == "dunning"

    async def test_een_pakket_van_een_andere_klant_telt_niet(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock, db: Any
    ) -> None:
        """Het pakket staat voor klant A aan; een uitvoering van klant B krijgt er niets van."""
        _zet_pakket(db, gebruikers.tenant_a, "mkb.zero_admin", True)
        van_b = str(gebruikers.beheerder_van_b)

        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("vatcompliance"), {}, tenant_id=gebruikers.tenant_b, starter=van_b
            )

        assert "niet aan" in str(fout.value)


@pytest.mark.asyncio
class TestEenStoringInDeControleIsGeenOpenDeur:
    async def test_een_databasefout_in_de_pakketcontrole_geeft_een_nette_reden_zonder_ruwe_tekst(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        editor = str(gebruikers.per_rol["editor"])

        with patch(
            "src.core.als.agents.workflow_stap._pakket_staat_aan",
            AsyncMock(side_effect=RuntimeError("password=geheim host=intern.example")),
        ):
            with pytest.raises(StapMislukt) as fout:
                await _engine()._execute_agent_task(
                    _stap("vatcompliance"), {}, tenant_id=gebruikers.tenant_a, starter=editor
                )

        assert "konden niet worden gecontroleerd" in str(fout.value)
        assert "geheim" not in str(fout.value)
        assert taalmodel.generate.await_count == 0


@pytest.mark.asyncio
class TestDeApiBiedtAlleenUitvoerbareAgentsAan:
    async def test_de_lijst_voor_de_bouwer_is_de_uitvoerbare_lijst_van_deze_klant(
        self, als_applicatierol: None, gebruikers: Gebruikers
    ) -> None:
        from types import SimpleNamespace

        from src.core.api.v1.workflow.workflow_generation_router import list_executable_agents

        antwoord = await list_executable_agents(
            request=_verzoek(),  # type: ignore[arg-type]
            current_user=SimpleNamespace(tenant_id=gebruikers.tenant_a),  # type: ignore[arg-type]
        )

        assert sorted(a["agent_id"] for a in antwoord["agents"]) == [  # type: ignore[attr-defined,union-attr]
            "dunning",
            "receiptscanner",
            "skillsgaptraining",
            "vatcompliance",
        ]

    async def test_een_agent_waarvan_het_pakket_uit_staat_wordt_niet_aangeboden(
        self, als_applicatierol: None, gebruikers: Gebruikers, db: Any
    ) -> None:
        from types import SimpleNamespace

        from src.core.api.v1.workflow.workflow_generation_router import list_executable_agents

        _zet_pakket(db, gebruikers.tenant_a, "mkb.zero_admin", False)

        antwoord = await list_executable_agents(
            request=_verzoek(),  # type: ignore[arg-type]
            current_user=SimpleNamespace(tenant_id=gebruikers.tenant_a),  # type: ignore[arg-type]
        )

        assert sorted(a["agent_id"] for a in antwoord["agents"]) == [  # type: ignore[attr-defined,union-attr]
            "dunning",
            "skillsgaptraining",
        ]


@pytest.mark.asyncio
class TestEenStoringInDeAgentLektGeenRuweTekst:
    async def test_een_onverwachte_fout_in_de_agent_geeft_een_vaste_reden(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        taalmodel.generate.side_effect = RuntimeError("password=geheim host=intern.example")
        editor = str(gebruikers.per_rol["editor"])

        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=editor
            )

        assert "geheim" not in str(fout.value) and "storing" in str(fout.value)
        assert fout.value.tijdelijk is False  # een onbekende fout wordt niet opnieuw geprobeerd (kost taalmodelgeld)

    async def test_te_veel_verzoeken_bij_het_taalmodel_zegt_dat_wachten_helpt(
        self, als_applicatierol: None, gebruikers: Gebruikers, taalmodel: AsyncMock
    ) -> None:
        import httpx

        verzoek = httpx.Request("POST", "https://api.example/v1/chat")
        taalmodel.generate.side_effect = httpx.HTTPStatusError(
            "Client error 429 password=geheim",
            request=verzoek,
            response=httpx.Response(429, request=verzoek),
        )
        editor = str(gebruikers.per_rol["editor"])

        with pytest.raises(StapMislukt) as fout:
            await _engine()._execute_agent_task(
                _stap("dunning"), {}, tenant_id=gebruikers.tenant_a, starter=editor
            )

        assert "te veel verzoeken" in str(fout.value) and "geheim" not in str(fout.value)
        assert fout.value.tijdelijk is True  # te druk is tijdelijk: een nieuwe poging mag, met een maximum


class TestDeSkillWordtNaAfloopNietBewaard:
    def test_de_standaard_van_de_runtime_interface_weigert(self) -> None:
        import asyncio

        from src.core.workflow.interfaces import IAgentRuntime

        class _Kaal(ProductionAgentRuntime):
            run_agentstap = IAgentRuntime.run_agentstap  # type: ignore[assignment]

        uitkomst = asyncio.run(_Kaal().run_agentstap("dunning", "x", {}, "1"))

        assert uitkomst["success"] is False
