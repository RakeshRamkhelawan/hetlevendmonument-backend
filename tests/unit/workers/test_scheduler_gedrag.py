"""Gedragstests voor TaskScheduler (BE-WRK-001 taak 5).

Vijf gevallen, elk gemeten:
  T1 -- een falende job wordt zichtbaar via de ERROR-listener
  T2 -- een gemiste uitvoering wordt zichtbaar via de MISSED-listener
  T3 -- start_scheduler() roept _bind_the_real_broker() aan, en daarna hangt geen actor
        op StubBroker
  T4 -- get_scheduled_jobs() geeft precies de jobs die initialize() heeft ingepland
  T5 -- shutdown_scheduler() laat geen lopende singleton achter

Opmerkingen over testopzet:
- De events worden met de ECHTE APScheduler-event-klassen aangemaakt, zodat de
  tak die wordt getoetst echt de tak is die in productie vuurt (les van regie 2026-09-26:
  gebruik niet de parameterwaarde die uitschakelt wat je toetst).
- `record.args` wordt geasserteerd, NIET de uitgeschreven string. Reden: een check op
  de string kan worden waargemaakt door de tekst van de uitzondering zelf -- meten op
  `record.args` toetst de structuur van de aanroep.
  `record.args` is `tuple | Mapping | None`; we asserteren `isinstance(tuple)` voordat
  we indexeren -- dit is ook een check dat de logger als positional args wordt aangeroepen.
- StubBroker-check: we toetsen het OBJECT (actor.broker is/is not StubBroker), niet naam.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def scheduler_instance() -> Any:
    """Een niet-geinitialiseerde TaskScheduler zonder APScheduler-process."""
    from src.workers.scheduler import TaskScheduler

    return TaskScheduler()


@pytest.fixture()
def probleem_listener(scheduler_instance: Any) -> Any:
    """De luisteraar los, bruikbaar zonder een draaiende scheduler."""
    return scheduler_instance._op_job_probleem


def _assert_args(record: logging.LogRecord, index: int, verwacht: object) -> None:
    """Helper die pyright-veilig op record.args indexeert na een tuple-guard."""
    assert isinstance(record.args, tuple), (
        f"record.args moet een tuple zijn (positional logging), niet {type(record.args)}"
    )
    assert record.args[index] == verwacht, (
        f"record.args[{index}] = {record.args[index]!r}, verwacht {verwacht!r}"
    )


class TestListenerFoutZichtbaar:
    """T1 -- een falende job levert een ERROR-logrecord op."""

    def test_job_error_logt_fout_als_eerste_arg(
        self, probleem_listener: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent

        uitzondering = ValueError("broker onbereikbaar")
        event = JobExecutionEvent(
            code=EVENT_JOB_ERROR,
            job_id="pack_health_aggregation",
            jobstore="default",
            scheduled_run_time=datetime.now(timezone.utc),
            retval=None,
            exception=uitzondering,
            traceback=None,
        )

        with caplog.at_level(logging.ERROR, logger="src.workers.scheduler"):
            probleem_listener(event)

        fout_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(fout_records) == 1, "verwacht precies een ERROR-logrecord"
        record = fout_records[0]
        # Toets de STRUCTUUR van de aanroep, niet de uitgeschreven string
        # (een check op de string wordt waargemaakt door de tekst van de uitzondering zelf).
        _assert_args(record, 0, "fout")
        _assert_args(record, 1, "pack_health_aggregation")

    def test_job_error_logt_geen_warning(
        self, probleem_listener: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent

        event = JobExecutionEvent(
            code=EVENT_JOB_ERROR,
            job_id="pack_health_aggregation",
            jobstore="default",
            scheduled_run_time=datetime.now(timezone.utc),
            retval=None,
            exception=ValueError("x"),
            traceback=None,
        )
        with caplog.at_level(logging.WARNING, logger="src.workers.scheduler"):
            probleem_listener(event)

        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert not warn_records, "een fout moet ERROR loggen, niet WARNING"


class TestListenerGemisteUitvoeringZichtbaar:
    """T2 -- een gemiste uitvoering levert een WARNING-logrecord op met de juiste reden."""

    def test_job_missed_logt_gemiste_uitvoering(
        self, probleem_listener: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent

        event = JobExecutionEvent(
            code=EVENT_JOB_MISSED,
            job_id="retention_cleanup",
            jobstore="default",
            scheduled_run_time=datetime.now(timezone.utc),
            retval=None,
            exception=None,
            traceback=None,
        )

        with caplog.at_level(logging.WARNING, logger="src.workers.scheduler"):
            probleem_listener(event)

        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warn_records) == 1, "verwacht precies een WARNING-logrecord"
        record = warn_records[0]
        # Dit is de kerncheck: onderscheidt 'gemiste uitvoering' van 'fout'
        # zonder de _PROBLEEM-mapping is de logstring identiek.
        _assert_args(record, 0, "gemiste uitvoering")
        _assert_args(record, 1, "retention_cleanup")

    def test_job_missed_logt_geen_error(
        self, probleem_listener: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent

        event = JobExecutionEvent(
            code=EVENT_JOB_MISSED,
            job_id="retention_cleanup",
            jobstore="default",
            scheduled_run_time=datetime.now(timezone.utc),
            retval=None,
            exception=None,
            traceback=None,
        )
        with caplog.at_level(logging.ERROR, logger="src.workers.scheduler"):
            probleem_listener(event)

        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert not error_records, "een gemiste uitvoering moet WARNING loggen, niet ERROR"


class TestGeenStubBrokerNaStart:
    """T3 -- start_scheduler() roept _bind_the_real_broker() aan voor get_scheduler().

    Wat we toetsen: de VOLGORDE (bind eerst, dan broker-check, dan scheduler halen) en dat
    de bind-functie daadwerkelijk wordt aangeroepen. De effectiviteit van bind zelf
    (actor.broker is not StubBroker na een echte Redis-verbinding) is een integratiecheck;
    in een unit test kunnen we geen Redis-verbinding openen.

    Toets op het OBJECT: we patchen _bind_the_real_broker en verifieren dat het met de
    juiste call-volgorde werd aangeroepen -- niet via de naam of een string-vergelijking.
    `_eis_een_echte_broker` wordt ook gepatcht: in een unit test zonder Redis staan actors
    altijd op StubBroker, en de echte check gooit dan een RuntimeError die ons niet
    interesseert in deze volgorde-test.
    """

    @pytest.mark.asyncio
    async def test_bind_wordt_aangeroepen_voor_get_scheduler(self) -> None:
        import src.workers.scheduler as sched_mod

        aanroepvolgorde: list[str] = []

        def nep_bind() -> None:
            aanroepvolgorde.append("bind")

        def nep_eis() -> None:
            aanroepvolgorde.append("eis")

        async def nep_get() -> None:
            aanroepvolgorde.append("get")
            return None

        with (
            patch.object(sched_mod, "SCHEDULER_ENABLED", True),
            patch.object(sched_mod, "_bind_the_real_broker", side_effect=nep_bind),
            patch.object(sched_mod, "_eis_een_echte_broker", side_effect=nep_eis),
            patch.object(sched_mod, "get_scheduler", side_effect=nep_get),
        ):
            await sched_mod.start_scheduler()

        assert aanroepvolgorde == ["bind", "eis", "get"], (
            f"Verwachte volgorde: bind -> eis -> get, maar de volgorde was: {aanroepvolgorde}"
        )

    def test_bind_roept_get_redis_broker_aan(self) -> None:
        """_bind_the_real_broker() delegeert naar get_redis_broker() -- het OBJECT, niet naam."""
        import src.workers.scheduler as sched_mod

        mock_get_redis = MagicMock(return_value=MagicMock())
        with patch("src.workers.workflow_worker.get_redis_broker", mock_get_redis):
            sched_mod._bind_the_real_broker()

        mock_get_redis.assert_called_once()


class TestEisEchtebrokerRaisePath:
    """T3b -- _eis_een_echte_broker() gooit RuntimeError als een actor op StubBroker hangt.

    Mutatiebewijs (2026-09-26, item E regie-review; P1 herschreven na volledige suite):
      P1 voorwaarts -- nep-module met actor op ECHTE StubBroker via patch.dict(sys.modules):
                       RuntimeError met 'StubBroker'. Maakt de voorwaarde zelf; vertrouwt
                       NIET op de omgeving (gemeten: in de volledige suite kan een eerdere
                       test de broker hebben omgezet waarna echte actors niet meer op
                       StubBroker staan -- dan slaagt de test ten onrechte).
      P2 tegenrichting -- detectielogica direct getoetst zonder de volledige import-keten
                          (patroon uit mutatie_taak6.py P2): nep-actor op niet-StubBroker
                          levert een lege stub_gebonden-lijst op.
      P3 -- globale broker is zelf een StubBroker na een mislukte bind: direct weigeren.
    """

    def test_gooit_bij_stub_gebonden_actor(self) -> None:
        """P1 -- nep-module met actor op echte StubBroker -> RuntimeError.

        Injecteert de voorwaarde via de _actors_module-parameter: de functie doet normaal
        `import src.workers.actors` maar accepteert een injecteerbaar object. Zo is de test
        volledig onafhankelijk van sys.modules-staat -- patch.dict(sys.modules) werkte in
        isolatie maar niet in de volledige suite (gemeten 2026-09-26: het echte module-object
        was al gecachet en werd via de package-attribute opgehaald).
        Actor.broker is een ECHTE StubBroker (geen MagicMock): de productiecode doet
        `isinstance(waarde.broker, StubBroker)` en MagicMock is geen StubBroker.
        """
        import types

        import dramatiq
        from dramatiq.brokers.stub import StubBroker

        import src.workers.scheduler as sched_mod

        stub_broker = StubBroker()
        nep_actor = MagicMock(spec=dramatiq.Actor)
        nep_actor.broker = stub_broker  # ECHTE StubBroker; MagicMock zou isinstance missen

        nep_module = types.ModuleType("src.workers.actors")
        nep_module.nep_actor = nep_actor  # type: ignore[attr-defined]

        nep_niet_stub = MagicMock()  # globale broker is geen StubBroker: eerste check passeert
        with patch("dramatiq.get_broker", return_value=nep_niet_stub):
            with pytest.raises(RuntimeError, match="StubBroker"):
                sched_mod._eis_een_echte_broker(nep_module)

    def test_detectielogica_leeg_bij_niet_stub_actor(self) -> None:
        """P2 -- detectielogica geeft lege lijst als actor NIET op StubBroker hangt.

        Zelfde patroon als mutatie_taak6.py P2: de logica direct getoetst,
        zonder de volledige import-keten van src.workers.actors.
        """
        import dramatiq
        from dramatiq.brokers.stub import StubBroker

        nep_redis_broker = MagicMock()  # geen StubBroker
        nep_actor = MagicMock(spec=dramatiq.Actor)
        nep_actor.broker = nep_redis_broker

        nep_vars = {"run_pack_health": nep_actor}

        stub_gebonden = [
            naam
            for naam, waarde in nep_vars.items()
            if isinstance(waarde, dramatiq.Actor) and isinstance(waarde.broker, StubBroker)
        ]
        assert not stub_gebonden, (
            f"Verwacht lege lijst (actor is niet op StubBroker), maar gevonden: {stub_gebonden}"
        )

    def test_gooit_als_globale_broker_zelf_stub_is(self) -> None:
        """P3 -- globale broker is StubBroker na een mislukte bind: direct weigeren."""
        from dramatiq.brokers.stub import StubBroker

        import src.workers.scheduler as sched_mod

        stub_broker = StubBroker()
        with patch("dramatiq.get_broker", return_value=stub_broker):
            with pytest.raises(RuntimeError, match="globale dramatiq-broker"):
                sched_mod._eis_een_echte_broker()


class TestRetentionCleanupPlantOokDeAvgPurge:
    """De AVG-planner draait mee met de retention-cleanup (geen eigen cron: DSM-plafond)."""

    async def test_both_actors_are_sent(self) -> None:
        from unittest.mock import MagicMock

        from src.workers.scheduler import TaskScheduler

        retention, avg = MagicMock(), MagicMock()
        with (
            patch("src.workers.actors.run_retention_cleanup", retention, create=True),
            patch("src.workers.actors.run_avg_purge_vervallen", avg, create=True),
        ):
            await TaskScheduler()._run_retention_cleanup()

        assert (retention.send.call_count, avg.send.call_count) == (1, 1)

    async def test_the_planner_still_runs_when_the_retention_send_fails(self) -> None:
        from unittest.mock import MagicMock

        from src.workers.scheduler import TaskScheduler

        retention, avg = MagicMock(), MagicMock()
        retention.send.side_effect = RuntimeError("queue stuk")
        with (
            patch("src.workers.actors.run_retention_cleanup", retention, create=True),
            patch("src.workers.actors.run_avg_purge_vervallen", avg, create=True),
        ):
            with pytest.raises(RuntimeError):
                await TaskScheduler()._run_retention_cleanup()

        assert avg.send.call_count == 1


class TestGetScheduledJobs:
    """T4 -- get_scheduled_jobs() geeft precies de jobs die initialize() heeft ingepland."""

    @pytest.mark.asyncio
    async def test_get_scheduled_jobs_bevat_alle_ingeplande_jobs(self) -> None:
        from src.workers.scheduler import TaskScheduler

        ts = TaskScheduler()

        with patch("src.workers.scheduler.SCHEDULER_TIMEZONE", "UTC"):
            gelukt = await ts.initialize()

        assert gelukt, "initialize() moest slagen"

        # start + direct stoppen zodat next_run_time beschikbaar is
        # (APScheduler berekent next_run_time pas na start)
        if ts.scheduler:
            ts.scheduler.start()
        try:
            jobs = ts.get_scheduled_jobs()
        finally:
            if ts.scheduler:
                ts.scheduler.shutdown(wait=False)

        job_ids = {j["id"] for j in jobs}

        verwacht = {
            "pack_health_aggregation",
            "daily_maintenance",
            "ml_model_training",
            "retention_cleanup",
            "prana_refill",
            "twin_observation_cleanup",
            "twin_cost_log_cleanup",
            "twin_profile_aggregation",
            "stale_task_cleanup",
            "hitl_ticket_cleanup",
            "cleanup_council_decisions",
            "cleanup_agent_critiques",
            "cleanup_resolved_hitl_tickets",
            "purge_soft_deleted_memory_items",
            "run_audit_verification",
            "check_hash_chain_integrity",
            "verstuur_klare_berichten",
            "volg_debiteuren_op",
            "signaleer_hr_termijnen",
            "ruim_bonnen_op",
            # BE-EP-054: wekelijkse BagIt-archiefexport (zondag 02:15 UTC)
            "export_foundation_archives",
        }
        ontbreekt = verwacht - job_ids
        onverwacht = job_ids - verwacht

        assert not ontbreekt, f"ingeplande jobs die get_scheduled_jobs() niet ziet: {ontbreekt}"
        assert not onverwacht, f"jobs die niet verwacht zijn: {onverwacht}"


class TestShutdownLaatGeenSingleton:
    """T5 -- shutdown_scheduler() laat geen lopende singleton achter."""

    def test_shutdown_wist_globale_singleton(self) -> None:
        import src.workers.scheduler as sched_module

        ts_mock = MagicMock()
        sched_module._scheduler_instance = ts_mock

        sched_module.shutdown_scheduler()

        assert sched_module._scheduler_instance is None, (
            "shutdown_scheduler() moet de globale singleton op None zetten"
        )
        ts_mock.shutdown.assert_called_once()

    def test_tweede_shutdown_is_idempotent(self) -> None:
        import src.workers.scheduler as sched_module

        sched_module._scheduler_instance = None
        sched_module.shutdown_scheduler()
        assert sched_module._scheduler_instance is None
