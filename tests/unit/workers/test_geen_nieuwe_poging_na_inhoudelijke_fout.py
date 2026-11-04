"""Een uitvoering of stap die om een INHOUDELIJKE reden faalt wordt niet opnieuw geprobeerd (workflowscherm nazorg, punt 1).

Gemeten op de ontwikkelstack (acceptant agentstap dag 2): een agentstap die faalde kostte ongeveer 37 seconden en meerdere
taalmodelaanroepen, omdat twee lagen opnieuw probeerden:

1. de engine probeerde elke mislukte stap tot `max_retries` (standaard 3) keer opnieuw met uitstel, ongeacht de reden;
2. de werker (dramatiq) bood de hele uitvoering opnieuw aan (3 of 5 keer), ook als de engine hem al op `failed` had gezet
   (daarna volgde `Invalid task state transition: failed -> running`).

Nu geldt: alleen een TIJDELIJKE fout (netwerk, time-out, 429 of 502/503/504, een hervatbare noodstop) krijgt een nieuwe
poging, met een maximum. Alles wat niet bekend is als tijdelijk (validatie, rechten, een weigering, een mislukte stap) geeft
nul nieuwe pogingen: onbekend is bij geldkosten "niet opnieuw".

Mutatiebewijs (2026-10-26): zie de eindmelding van de sessie.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.core.llm.llm_client import LLMRateLimitError as LLMRateLimitClient
from src.core.noodstop.guard import KlantStilgezet
from src.core.services.llm.base import LLMRateLimitError as LLMRateLimitServices
from src.core.workflow.engine import ProductionWorkflowEngine, StapMislukt
from src.core.workflow.foutsoort import is_tijdelijke_fout, moet_opnieuw
from src.core.workflow.interfaces import TaskExecutionResult


def _http_fout(status: int) -> httpx.HTTPStatusError:
    verzoek = httpx.Request("POST", "https://api.example/v1/chat")
    return httpx.HTTPStatusError(
        "fout", request=verzoek, response=httpx.Response(status, request=verzoek)
    )


class TestWelkeFoutenTijdelijkZijn:
    @pytest.mark.parametrize(
        "fout",
        [
            asyncio.TimeoutError(),
            TimeoutError("verbinding"),
            ConnectionError("verbroken"),
            ConnectionResetError("reset"),
            httpx.ConnectError("geen verbinding"),
            httpx.ReadTimeout("te langzaam"),
            _http_fout(429),
            _http_fout(502),
            _http_fout(503),
            _http_fout(504),
            _http_fout(408),
            LLMRateLimitServices("mistral: te veel verzoeken (429)"),
            LLMRateLimitClient("te druk"),
        ],
    )
    def test_dit_is_tijdelijk(self, fout: BaseException) -> None:
        assert is_tijdelijke_fout(fout) is True

    @pytest.mark.parametrize(
        "fout",
        [
            ValueError("ongeldige invoer"),
            KeyError("sleutel"),
            PermissionError("geen recht"),
            RuntimeError("Stap n1 is mislukt: de agent weigerde"),
            StapMislukt("het pakket staat uit"),
            _http_fout(400),
            _http_fout(401),
            _http_fout(403),
            _http_fout(404),
            _http_fout(422),
            _http_fout(500),
            FileNotFoundError("weg"),
            Exception("onbekend"),
            # Tekst van een medewerker die in een foutmelding terugkomt maakt een fout niet tijdelijk (Gate 2 security).
            RuntimeError("mistral: te veel verzoeken (429)"),
            RuntimeError("Too Many Requests"),
            ValueError("de stap 'Te veel verzoeken' heeft geen opdracht"),
        ],
    )
    def test_dit_is_inhoudelijk(self, fout: BaseException) -> None:
        assert is_tijdelijke_fout(fout) is False

    def test_een_tijdelijke_fout_in_een_andere_fout_wordt_herkend(self) -> None:
        try:
            try:
                raise _http_fout(429)
            except httpx.HTTPStatusError as oorzaak:
                raise RuntimeError("LLM aanroep mislukt") from oorzaak
        except RuntimeError as verpakt:
            assert is_tijdelijke_fout(verpakt) is True

    def test_een_stap_die_zelf_zegt_dat_hij_tijdelijk_faalde_telt_als_tijdelijk(self) -> None:
        assert is_tijdelijke_fout(StapMislukt("te druk", tijdelijk=True)) is True

    def test_een_stap_die_zelf_zegt_dat_hij_niet_tijdelijk_is_wint_van_de_oorzaak(self) -> None:
        fout = StapMislukt("gewogen", tijdelijk=False)
        fout.__cause__ = _http_fout(503)

        assert is_tijdelijke_fout(fout) is False

    def test_een_hervatbare_noodstop_is_tijdelijk(self) -> None:
        assert is_tijdelijke_fout(KlantStilgezet(1)) is True

    def test_een_uitvoering_die_al_is_beeindigd_wordt_nooit_opnieuw_aangeboden(self) -> None:
        fout = ConnectionError("verbroken")
        fout.uitvoering_beeindigd = True  # type: ignore[attr-defined]

        assert is_tijdelijke_fout(fout) is False

    def test_een_oneindige_oorzaakketen_loopt_niet_vast(self) -> None:
        een = RuntimeError("a")
        twee = RuntimeError("b")
        een.__cause__ = twee
        twee.__cause__ = een

        assert is_tijdelijke_fout(een) is False


class TestAlleenDeOorzaakTelt:
    def test_een_inhoudelijke_fout_tijdens_het_afhandelen_van_een_netwerkfout_is_niet_tijdelijk(self) -> None:
        try:
            try:
                raise ConnectionError("verbroken")
            except ConnectionError:
                raise ValueError("ongeldige invoer")  # noqa: B904 - bewust zonder `from`: dit toetst __context__
        except ValueError as fout:
            assert is_tijdelijke_fout(fout) is False


class TestDeInstellingenVanEenWorkflowZijnBegrensd:
    @pytest.mark.parametrize(("ingesteld", "verwacht"), [(0, 0), (3, 3), (5, 5), (6, 5), (1000, 5), (-2, 0)])
    def test_max_retries_blijft_tussen_nul_en_vijf(self, ingesteld: int, verwacht: int) -> None:
        spec = _engine()._parse_spec("w", 1, {"tasks": {}, "max_retries": ingesteld})

        assert spec.max_retries == verwacht

    @pytest.mark.parametrize(("ingesteld", "verwacht"), [(0, 0), (5, 5), (60, 60), (61, 60), (100000, 60), (-1, 0)])
    def test_het_uitstel_blijft_tussen_nul_en_zestig_seconden(self, ingesteld: int, verwacht: int) -> None:
        spec = _engine()._parse_spec("w", 1, {"tasks": {}, "retry_backoff_seconds": ingesteld})

        assert spec.retry_backoff_seconds == verwacht

    def test_een_onleesbare_waarde_valt_terug_op_de_standaard(self) -> None:
        spec = _engine()._parse_spec("w", 1, {"tasks": {}, "max_retries": "veel", "retry_backoff_seconds": None})

        assert (spec.max_retries, spec.retry_backoff_seconds) == (3, 5)


class TestHetMaximumAantalPogingen:
    def test_een_tijdelijke_fout_krijgt_een_nieuwe_poging_binnen_het_maximum(self) -> None:
        assert moet_opnieuw(3)(0, ConnectionError("x")) is True

    def test_na_het_maximum_volgt_geen_nieuwe_poging(self) -> None:
        assert moet_opnieuw(3)(3, ConnectionError("x")) is False

    def test_een_inhoudelijke_fout_krijgt_nooit_een_nieuwe_poging(self) -> None:
        assert moet_opnieuw(3)(0, ValueError("x")) is False


class TestDeWerkerProbeertAlleenTijdelijkeFoutenOpnieuw:
    def test_de_uitvoeringsactor_heeft_een_regel_voor_nieuwe_pogingen(self) -> None:
        from src.workers.workflow_worker import execute_workflow_task

        regel = execute_workflow_task.options.get("retry_when")

        assert callable(regel) and regel(0, ValueError("inhoudelijk")) is False

    def test_de_uitvoeringsactor_probeert_een_netwerkfout_wel_opnieuw(self) -> None:
        from src.workers.workflow_worker import execute_workflow_task

        assert execute_workflow_task.options["retry_when"](0, ConnectionError("x")) is True

    def test_de_stapactor_heeft_dezelfde_regel(self) -> None:
        from src.workers.workflow_worker import execute_task_task

        regel = execute_task_task.options.get("retry_when")

        assert callable(regel) and regel(0, RuntimeError("Stap mislukt")) is False

    def test_de_stapactor_stopt_na_vijf_pogingen(self) -> None:
        from src.workers.workflow_worker import execute_task_task

        assert execute_task_task.options["retry_when"](5, ConnectionError("x")) is False


def _engine() -> ProductionWorkflowEngine:
    engine = ProductionWorkflowEngine(
        llm_provider=MagicMock(), tool_broker=MagicMock(), agent_runtime=MagicMock()
    )
    engine._legacy_session = AsyncMock()  # type: ignore[assignment]
    engine._get_execution = AsyncMock(return_value=SimpleNamespace(id="e1", tasks_failed=0))  # type: ignore[method-assign]
    engine._get_task = AsyncMock(return_value=SimpleNamespace(retries=0))  # type: ignore[method-assign]
    engine._update_task_status = AsyncMock()  # type: ignore[method-assign]
    return engine


def _resultaat(*, tijdelijk: bool) -> TaskExecutionResult:
    return TaskExecutionResult(task_id="n1", success=False, error="stuk", tijdelijk=tijdelijk)


@pytest.mark.asyncio
class TestDeEngineProbeertEenStapNietOpnieuwBijEenInhoudelijkeFout:
    async def test_een_inhoudelijke_fout_geeft_een_uitvoering_van_de_stap(self) -> None:
        engine = _engine()
        engine.execute_task = AsyncMock(return_value=_resultaat(tijdelijk=False))  # type: ignore[method-assign]

        with (
            patch("src.core.workflow.engine.asyncio.sleep", AsyncMock()),
            pytest.raises(RuntimeError),
        ):
            await engine._execute_task_with_retry("x", "n1", {}, 3, 5)

        assert engine.execute_task.await_count == 1

    async def test_een_inhoudelijke_fout_wacht_niet(self) -> None:
        engine = _engine()
        engine.execute_task = AsyncMock(return_value=_resultaat(tijdelijk=False))  # type: ignore[method-assign]
        slaap = AsyncMock()

        with patch("src.core.workflow.engine.asyncio.sleep", slaap), pytest.raises(RuntimeError):
            await engine._execute_task_with_retry("x", "n1", {}, 3, 5)

        assert slaap.await_count == 0

    async def test_een_inhoudelijke_fout_telt_als_een_mislukte_stap(self) -> None:
        engine = _engine()
        engine.execute_task = AsyncMock(return_value=_resultaat(tijdelijk=False))  # type: ignore[method-assign]
        uitvoering = SimpleNamespace(id="e1", tasks_failed=0)
        engine._get_execution = AsyncMock(return_value=uitvoering)  # type: ignore[method-assign]

        with (
            patch("src.core.workflow.engine.asyncio.sleep", AsyncMock()),
            pytest.raises(RuntimeError),
        ):
            await engine._execute_task_with_retry("x", "n1", {}, 3, 5)

        assert uitvoering.tasks_failed == 1

    async def test_een_tijdelijke_fout_krijgt_het_maximum_aan_pogingen(self) -> None:
        engine = _engine()
        engine.execute_task = AsyncMock(return_value=_resultaat(tijdelijk=True))  # type: ignore[method-assign]

        with (
            patch("src.core.workflow.engine.asyncio.sleep", AsyncMock()),
            pytest.raises(RuntimeError),
        ):
            await engine._execute_task_with_retry("x", "n1", {}, 3, 5)

        assert engine.execute_task.await_count == 4

    async def test_een_tijdelijke_fout_die_daarna_slaagt_stopt_met_proberen(self) -> None:
        engine = _engine()
        goed = TaskExecutionResult(task_id="n1", success=True, output={})
        engine.execute_task = AsyncMock(side_effect=[_resultaat(tijdelijk=True), goed])  # type: ignore[method-assign]

        with patch("src.core.workflow.engine.asyncio.sleep", AsyncMock()):
            uitkomst = await engine._execute_task_with_retry("x", "n1", {}, 3, 5)

        assert uitkomst.success is True and engine.execute_task.await_count == 2


@pytest.mark.asyncio
class TestDeEngineZegtOfEenMislukteStapTijdelijkWas:
    async def _faal_met(self, fout: BaseException) -> TaskExecutionResult:
        engine = _engine()
        engine._parse_spec = MagicMock(  # type: ignore[method-assign]
            return_value=SimpleNamespace(tasks={"n1": {"type": "agent"}})
        )
        engine._get_completed_tasks = AsyncMock(return_value=[])  # type: ignore[method-assign]
        execution = SimpleNamespace(
            id="e1",
            tenant_id=5,
            input_json={},
            initiated_by="7",
            workflow=SimpleNamespace(workflow_id="w", version=1, spec_json={}),
            tasks_failed=0,
        )
        engine._get_execution = AsyncMock(return_value=execution)  # type: ignore[method-assign]
        engine._get_task = AsyncMock(return_value=SimpleNamespace(error_json=None))  # type: ignore[method-assign]
        engine._execute_agent_task = AsyncMock(side_effect=fout)  # type: ignore[method-assign]

        with patch("src.core.workflow.engine.eis_klant_actief", AsyncMock()):
            return await engine.execute_task("x", "n1")

    async def test_een_weigering_is_niet_tijdelijk(self) -> None:
        resultaat = await self._faal_met(StapMislukt("het pakket staat uit"))

        assert resultaat.tijdelijk is False

    async def test_een_stap_die_zelf_tijdelijk_meldt_is_tijdelijk(self) -> None:
        resultaat = await self._faal_met(StapMislukt("te druk", tijdelijk=True))

        assert resultaat.tijdelijk is True

    async def test_een_netwerkfout_is_tijdelijk(self) -> None:
        resultaat = await self._faal_met(ConnectionError("verbroken"))

        assert resultaat.tijdelijk is True

    async def test_een_gewone_fout_is_niet_tijdelijk(self) -> None:
        resultaat = await self._faal_met(ValueError("ongeldig"))

        assert resultaat.tijdelijk is False

    async def test_een_agentstap_die_tijdelijk_meldt_geeft_een_tijdelijke_stapfout(self) -> None:
        engine = _engine()
        engine.agent_runtime.run_agentstap = AsyncMock(  # type: ignore[method-assign]
            return_value={"success": False, "tijdelijk": True, "output": {"error": "te druk"}}
        )

        with pytest.raises(StapMislukt) as fout:
            await engine._execute_agent_task(
                {"agent_id": "dunning", "instruction": "x"}, {}, tenant_id=5, starter="7"
            )

        assert fout.value.tijdelijk is True

    async def test_een_agentstap_zonder_tijdelijk_signaal_is_een_inhoudelijke_stapfout(
        self,
    ) -> None:
        engine = _engine()
        engine.agent_runtime.run_agentstap = AsyncMock(  # type: ignore[method-assign]
            return_value={"success": False, "output": {"error": "gewogen"}}
        )

        with pytest.raises(StapMislukt) as fout:
            await engine._execute_agent_task(
                {"agent_id": "dunning", "instruction": "x"}, {}, tenant_id=5, starter="7"
            )

        assert fout.value.tijdelijk is False


@pytest.mark.asyncio
class TestEenBeeindigdeUitvoeringWordtNietOpnieuwAangeboden:
    async def test_de_fout_van_een_mislukte_uitvoering_draagt_het_merk_beeindigd(self) -> None:
        engine = _engine()
        uitvoering = SimpleNamespace(
            id="e1",
            execution_id="e1",
            tenant_id=5,
            input_json={},
            status=None,
            workflow=SimpleNamespace(workflow_id="w", version=1, spec_json={}),
        )
        engine._get_execution = AsyncMock(return_value=uitvoering)  # type: ignore[method-assign]
        engine._fail_execution = AsyncMock()  # type: ignore[method-assign]
        engine._parse_spec = MagicMock(side_effect=ConnectionError("verbroken"))  # type: ignore[method-assign]

        with patch("src.core.workflow.engine.eis_klant_actief", AsyncMock()):
            with pytest.raises(ConnectionError) as fout:
                await engine.execute_workflow("e1")

        assert getattr(fout.value, "uitvoering_beeindigd", False) is True
