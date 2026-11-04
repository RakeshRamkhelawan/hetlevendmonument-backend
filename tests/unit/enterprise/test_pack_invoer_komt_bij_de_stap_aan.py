"""`run_pack` en `run_pack_by_id` geven de gebruikersinvoer aan elke stap (ADR-036 OP-09).

Tot OP-09 kwam alleen `step.params` uit de YAML bij een stap aan, en de route gaf zelfs dat niet
door (zij gebruikte `execute_pack`, dat altijd `{}` meegeeft). De regel: `params` van een stap is
`{**step.params, "input": input_data}`, en zonder invoer blijft `params` precies `step.params`
(bestaande aanroepers veranderen niet).

De uitvoering van een stap (`_execute_step`) is op de grens vervangen; er is geen database of LLM.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest

from src.core.als.enterprise.packs import (
    DomainPack,
    DomainPackOrchestrator,
    Voortgang,
    WorkflowStep,
)
from src.core.shared.interfaces import ExecutionResult
from src.core.types import ExecutionStatusContract


@dataclass
class Opname:
    gezien: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    mislukt: set[str] = field(default_factory=set)


def _pack() -> DomainPack:
    return DomainPack(
        pack_id="test.pack",
        name="Testpack",
        steps=[
            WorkflowStep(agent_id="eerste", mode="sequential", params={"vast": 1}),
            WorkflowStep(agent_id="tweede", mode="parallel", params={"input": "uit-yaml"}),
            WorkflowStep(agent_id="derde", mode="parallel"),
        ],
    )


class TestInvoerBijDeStap:
    async def test_de_invoer_komt_als_input_bij_elke_stap_aan(self, opname: Opname) -> None:
        await DomainPackOrchestrator().run_pack(_pack(), 1, input_data={"factuur": "F-1"})

        assert [p.get("input") for _, p in opname.gezien] == [{"factuur": "F-1"}] * 3

    async def test_de_vaste_params_uit_de_yaml_blijven_staan(self, opname: Opname) -> None:
        await DomainPackOrchestrator().run_pack(_pack(), 1, input_data={"factuur": "F-1"})

        assert dict(opname.gezien)["eerste"] == {"vast": 1, "input": {"factuur": "F-1"}}

    async def test_de_gebruikersinvoer_wint_van_een_input_sleutel_in_de_yaml(
        self, opname: Opname
    ) -> None:
        await DomainPackOrchestrator().run_pack(_pack(), 1, input_data={"factuur": "F-1"})

        assert dict(opname.gezien)["tweede"]["input"] == {"factuur": "F-1"}

    async def test_de_yaml_zelf_wordt_niet_gewijzigd(self, opname: Opname) -> None:
        pack = _pack()

        await DomainPackOrchestrator().run_pack(pack, 1, input_data={"factuur": "F-1"})

        assert pack.steps[0].params == {"vast": 1}

    async def test_zonder_invoer_blijft_params_precies_step_params(self, opname: Opname) -> None:
        await DomainPackOrchestrator().run_pack(_pack(), 1)

        assert dict(opname.gezien)["eerste"] == {"vast": 1}

    async def test_een_mislukt_roi_logboek_maakt_een_gelukte_stap_niet_mislukt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Het ROI-logboek is een meting, geen onderdeel van het werk (best_effort).

        Gemeten 2026-10-09: de tabel `agent_execution_logs` bestaat in geen enkel model of
        migratie; zonder deze bescherming werd daardoor ELKE gelukte stap een mislukte stap.
        """
        from contextlib import asynccontextmanager

        from src.core.analytics.roi_service import ROIService
        from src.core.database.database import db_manager

        async def _gelukt(
            self: Any,
            agent_id: str,
            tenant_id: int,
            params: dict[str, Any],
            *,
            initiated_by_user_id: int | None = None,
        ) -> ExecutionResult:
            return ExecutionResult(
                task_id=agent_id,
                success=True,
                tenant_id=tenant_id,
                status=ExecutionStatusContract.KLAAR,
            )

        async def _kapot(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError('relation "agent_execution_logs" does not exist')

        @asynccontextmanager
        async def _geen_sessie() -> AsyncGenerator[None, None]:
            yield None

        monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", _gelukt)
        monkeypatch.setattr(ROIService, "record_run", _kapot)
        monkeypatch.setattr(db_manager, "get_session", _geen_sessie)

        resultaten = await DomainPackOrchestrator().run_pack(_pack(), 1)

        assert [r.success for r in resultaten] == [True, True, True]

    async def test_een_stap_die_te_lang_duurt_blijft_herkenbaar_aan_zijn_agent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Een time-out-resultaat zegt WELKE stap te traag was (`agent_id`), niet alleen 'timeout'."""
        import asyncio

        async def _traag(
            self: Any,
            agent_id: str,
            tenant_id: int,
            params: dict[str, Any],
            *,
            initiated_by_user_id: int | None = None,
        ) -> ExecutionResult:
            await asyncio.sleep(5)
            raise AssertionError("hoort door de SLA te zijn afgebroken")

        monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", _traag)

        async def _geen_meting(*_args: Any, **_kwargs: Any) -> None:
            return None

        # De run-meting (ROI) is hier niet het onderwerp; een mislukte stap wordt nu ook
        # vastgelegd en zou anders een echte database openen (ADR-036 OP-18).
        monkeypatch.setattr(DomainPackOrchestrator, "_leg_run_vast", _geen_meting)
        pack = DomainPack(
            pack_id="test.traag",
            name="Traag",
            steps=[WorkflowStep(agent_id="langzaam", mode="sequential", sla_seconds=0.05)],
        )

        (resultaat,) = await DomainPackOrchestrator().run_pack(pack, 1)

        assert (resultaat.task_id, resultaat.agent_id) == ("timeout", "langzaam")

    async def test_een_stap_die_een_fout_geeft_blijft_herkenbaar_aan_zijn_agent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _kapot(
            self: Any,
            agent_id: str,
            tenant_id: int,
            params: dict[str, Any],
            *,
            initiated_by_user_id: int | None = None,
        ) -> ExecutionResult:
            raise RuntimeError("stuk")

        monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", _kapot)

        async def _geen_meting(*_args: Any, **_kwargs: Any) -> None:
            return None

        # De run-meting (ROI) is hier niet het onderwerp; een mislukte stap wordt nu ook
        # vastgelegd en zou anders een echte database openen (ADR-036 OP-18).
        monkeypatch.setattr(DomainPackOrchestrator, "_leg_run_vast", _geen_meting)
        pack = DomainPack(
            pack_id="test.kapot",
            name="Kapot",
            steps=[WorkflowStep(agent_id="stukke-agent", mode="sequential")],
        )

        (resultaat,) = await DomainPackOrchestrator().run_pack(pack, 1)

        assert (resultaat.task_id, resultaat.agent_id) == ("error", "stukke-agent")

    async def test_run_pack_by_id_geeft_de_invoer_door(
        self, opname: Opname, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orchestrator = DomainPackOrchestrator()
        # De catalogus is een singleton: `setitem` ruimt na de test op, een directe toewijzing niet.
        monkeypatch.setitem(orchestrator.catalog.packs, "test.pack", _pack())  # type: ignore[arg-type]

        await orchestrator.run_pack_by_id("test.pack", 1, input_data={"factuur": "F-1"})

        assert [p.get("input") for _, p in opname.gezien] == [{"factuur": "F-1"}] * 3


@pytest.fixture
def opname(monkeypatch: pytest.MonkeyPatch) -> Opname:
    """Vervangt `_execute_step`; de agents in `Opname.mislukt` falen, de rest slaagt.

    Ook het ROI-logboek en de databasesessie zijn vervangen: er is geen database in deze tests.
    """
    opname = Opname()

    async def _stap(
        self: Any,
        agent_id: str,
        tenant_id: int,
        params: dict[str, Any],
        *,
        initiated_by_user_id: int | None = None,
    ) -> ExecutionResult:
        opname.gezien.append((agent_id, params))
        ok = agent_id not in opname.mislukt
        return ExecutionResult(
            task_id=agent_id,
            success=ok,
            error_message=None if ok else "bewust mislukt",
            tenant_id=tenant_id,
            agent_id=agent_id,
            status=ExecutionStatusContract.KLAAR if ok else ExecutionStatusContract.MISLUKT,
        )

    monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", _stap)

    async def _geen_roi(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("src.core.analytics.roi_service.ROIService.record_run", _geen_roi)

    @asynccontextmanager
    async def _geen_sessie() -> AsyncGenerator[None, None]:
        yield None

    from src.core.database.database import db_manager

    monkeypatch.setattr(db_manager, "get_session", _geen_sessie)
    return opname


def _keten(*stappen: tuple[str, str]) -> DomainPack:
    return DomainPack(
        pack_id="test.keten",
        name="Keten",
        # `m` is een kale str in de testdata; WorkflowStep valideert de Literal bij het bouwen.
        steps=[WorkflowStep(agent_id=a, mode=m) for a, m in stappen],  # type: ignore[arg-type]
    )


class TestAfbrekenBijFalen:
    """Een falende SEQUENTIELE stap breekt de keten af (besluit regie 2026-10-10).

    Reden: een btw-overzicht of aanmaning op basis van een mislukte bonverwerking is fout werk
    dat een klant moet terugdraaien. Gedekte stappen worden NIET uitgevoerd en staan als
    `skipped` in de resultaten, met de reden.
    """

    async def test_na_een_falende_sequentiele_stap_draaien_de_volgende_niet(
        self, opname: Opname
    ) -> None:
        opname.mislukt.add("b")

        await DomainPackOrchestrator().run_pack(
            _keten(("a", "sequential"), ("b", "sequential"), ("c", "sequential")), 1
        )

        assert [agent for agent, _ in opname.gezien] == ["a", "b"]

    async def test_de_overgeslagen_stappen_staan_in_de_resultaten_met_reden(
        self, opname: Opname
    ) -> None:
        opname.mislukt.add("b")

        resultaten = await DomainPackOrchestrator().run_pack(
            _keten(("a", "sequential"), ("b", "sequential"), ("c", "sequential")), 1
        )

        assert [(r.agent_id, r.task_id) for r in resultaten] == [
            ("a", "a"),
            ("b", "b"),
            ("c", "skipped"),
        ]
        # De reden noemt het volgnummer van de mislukte stap (b is stap 2), geen agentnaam: pakketten
        # nazorg punt 4, zie test_pack_overgeslagen_uitleg.py.
        assert resultaten[2].error_message == "Overgeslagen: stap 2 is mislukt"
        assert resultaten[2].success is False

    async def test_een_geslaagde_keten_slaat_niets_over(self, opname: Opname) -> None:
        resultaten = await DomainPackOrchestrator().run_pack(
            _keten(("a", "sequential"), ("b", "sequential")), 1
        )

        assert [r.task_id for r in resultaten] == ["a", "b"]

    async def test_een_falende_stap_na_een_parallel_blok_breekt_ook_af(
        self, opname: Opname
    ) -> None:
        opname.mislukt.add("q")

        resultaten = await DomainPackOrchestrator().run_pack(
            _keten(("p", "parallel"), ("q", "sequential"), ("r", "sequential")), 1
        )

        assert [r.task_id for r in resultaten] == ["p", "q", "skipped"]

    async def test_een_falende_parallelle_stap_breekt_niet_af(self, opname: Opname) -> None:
        """Bewust niet: de brief noemt alleen sequentiele stappen; parallelle stappen zijn los."""
        opname.mislukt.add("x")

        resultaten = await DomainPackOrchestrator().run_pack(
            _keten(("x", "parallel"), ("y", "parallel"), ("z", "sequential")), 1
        )

        assert [r.task_id for r in resultaten] == ["x", "y", "z"]


class TestVoortgang:
    """`Voortgang` legt per stap-index vast wat klaar is en wat gestart is, TERWIJL de run loopt.

    De route heeft dit nodig om bij een time-out van de hele run eerlijk te melden wat er
    gebeurd is: klaar (met resultaat), begonnen maar niet klaar, of nooit begonnen.
    """

    @staticmethod
    def _traag(traag: set[str]) -> Any:
        import asyncio

        async def _stap(
            self: Any,
            agent_id: str,
            tenant_id: int,
            params: dict[str, Any],
            *,
            initiated_by_user_id: int | None = None,
        ) -> ExecutionResult:
            if agent_id in traag:
                await asyncio.sleep(5)
            return ExecutionResult(
                task_id=agent_id, success=True, tenant_id=tenant_id, agent_id=agent_id
            )

        return _stap

    async def test_een_sequentiele_run_toont_wat_klaar_is_en_wat_liep(
        self, monkeypatch: pytest.MonkeyPatch, opname: Opname
    ) -> None:
        """`opname` levert alleen de vervangen ROI-log en databasesessie; `_execute_step` wordt
        hieronder opnieuw vervangen."""
        import asyncio

        monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", self._traag({"traag"}))
        voortgang = Voortgang()

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                DomainPackOrchestrator().run_pack(
                    _keten(("snel", "sequential"), ("traag", "sequential"), ("laat", "sequential")),
                    1,
                    voortgang=voortgang,
                ),
                timeout=0.3,
            )

        assert (sorted(voortgang.klaar), sorted(voortgang.gestart)) == ([0], [0, 1])

    async def test_een_parallel_blok_bewaart_de_gelukte_stappen_bij_afbreken(
        self, monkeypatch: pytest.MonkeyPatch, opname: Opname
    ) -> None:
        """Hier zat het gat: het blok werd pas na `gather` vastgelegd, dus een gelukte stap
        ging verloren en kreeg in het antwoord de reden 'overgeslagen'."""
        import asyncio

        monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", self._traag({"y"}))
        voortgang = Voortgang()

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                DomainPackOrchestrator().run_pack(
                    _keten(("x", "parallel"), ("y", "parallel"), ("z", "sequential")),
                    1,
                    voortgang=voortgang,
                ),
                timeout=0.3,
            )

        assert (sorted(voortgang.klaar), sorted(voortgang.gestart)) == ([0], [0, 1])

    async def test_een_stap_is_klaar_voor_het_roi_logboek_loopt(
        self, monkeypatch: pytest.MonkeyPatch, opname: Opname
    ) -> None:
        """Een trage meting mag een gelukte stap niet 'onderbroken' laten heten."""
        import asyncio

        from src.core.analytics.roi_service import ROIService

        async def _trage_roi(*_args: Any, **_kwargs: Any) -> None:
            await asyncio.sleep(5)

        monkeypatch.setattr(DomainPackOrchestrator, "_execute_step", self._traag(set()))
        monkeypatch.setattr(ROIService, "record_run", _trage_roi)
        voortgang = Voortgang()

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                DomainPackOrchestrator().run_pack(
                    _keten(("a", "sequential")), 1, voortgang=voortgang
                ),
                timeout=0.3,
            )

        assert sorted(voortgang.klaar) == [0]
