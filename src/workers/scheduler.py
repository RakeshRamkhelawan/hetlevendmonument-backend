"""
Task Scheduler for Background Jobs

This module provides scheduled task execution using APScheduler.
It schedules recurring jobs like pack health aggregation, cleanup tasks, etc.

The scheduler uses Dramatiq to enqueue tasks, which are then processed
by the worker processes. This architecture provides:
- Reliable task execution with retries
- Horizontal scalability (add more workers as needed)
- Separation of scheduling from execution

Usage:
    # Start the scheduler
    python -m src.workers.scheduler

    # Or import and start programmatically
    from src.workers.scheduler import start_scheduler
    scheduler = await start_scheduler()
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

from src.core.noodstop import model_deur  # noqa: F401  (opstartpunt: meldt de noodstopcontrole van de modeldeur aan)

if TYPE_CHECKING:
    from apscheduler.events import JobEvent

logger = logging.getLogger(__name__)

# Scheduler configuration
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "UTC")

# Tijdzone PER TRIGGER, altijd expliciet (plan-van-aanpak-nazorg deel II punt 2).
#
# Waarom niet de schedulerzone: APScheduler 3.x geeft `AsyncIOScheduler(timezone=...)` alleen
# door aan een trigger die als tekst wordt meegegeven (`trigger="cron"`). Een
# `CronTrigger(...)`-instantie zonder `timezone` valt terug op `get_localzone()`: UTC in de
# container, Europe/Amsterdam op de Windows-ontwikkelmachine. Het log zei toch "(UTC)".
#
# De indeling:
# - KLANT_TIMEZONE (Europe/Amsterdam): jobs die de klant merkt en die hij in kantoortijd
#   denkt -- debiteuren opvolgen (04:15) en goedgekeurde berichten versturen.
# - ONDERHOUD_TIMEZONE (UTC): onderhoud, retentie, controles, aggregaties en de dagelijkse
#   prana-reset. UTC kent geen zomer- en wintertijd, dus geen overgeslagen of dubbele run.
#
# Zomer-/wintertijd: in Europe/Amsterdam springt de klok tussen 02:00 en 03:00 lokaal. Geen
# klantjob staat in dat venster (04:15 en elke minuut). Pack health om 02:00 draait in UTC en
# valt dus niet in dat venster (02:00 UTC is 03:00 of 04:00 lokaal); hij hoeft niet te
# verschuiven. `tests/unit/workers/test_scheduler_tijdzone.py` faalt als een CronTrigger
# geen tijdzone heeft.
KLANT_TIMEZONE = "Europe/Amsterdam"
ONDERHOUD_TIMEZONE = "UTC"

PACK_HEALTH_SCHEDULE = {
    "hour": 2,
    "minute": 0,
}  # Daily at 02:00 AM


class TaskScheduler:
    """
    APScheduler-based task scheduler for background jobs.

    This scheduler uses APScheduler for timing and Dramatiq for task execution.
    Tasks are enqueued to Redis and processed by worker processes.
    """

    def __init__(self) -> None:
        self.scheduler: Any | None = None  # TODO(TYPE): replace Any with concrete type
        self._running = False

    async def initialize(self) -> bool:
        """
        Initialize the scheduler with all scheduled jobs.

        Returns:
            True if initialization succeeded, False otherwise
        """
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger

            _sched = AsyncIOScheduler(
                timezone=SCHEDULER_TIMEZONE,
                job_defaults={
                    "misfire_grace_time": 3600,
                    "coalesce": True,
                    "max_instances": 1,
                },
            )
            self.scheduler = _sched

            from apscheduler.events import (
                EVENT_JOB_ERROR,
                EVENT_JOB_MAX_INSTANCES,
                EVENT_JOB_MISSED,
            )

            _sched.add_listener(
                self._op_job_probleem,
                EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES,
            )

            # Schedule pack health aggregation (daily at 02:00 AM)
            _sched.add_job(
                self._run_pack_health_job,
                trigger=CronTrigger(**PACK_HEALTH_SCHEDULE, timezone=ONDERHOUD_TIMEZONE),
                id="pack_health_aggregation",
                name="Pack Health Aggregation",
                replace_existing=True,
            )

            # Schedule daily maintenance (daily at 03:00 AM)
            _sched.add_job(
                self._run_daily_maintenance,
                trigger=CronTrigger(hour=3, minute=0, timezone=ONDERHOUD_TIMEZONE),
                id="daily_maintenance",
                name="Daily Maintenance",
                replace_existing=True,
            )

            # Schedule ML model training (daily at 03:30 AM - after pack health)
            _sched.add_job(
                self._run_ml_model_training,
                trigger=CronTrigger(hour=3, minute=30, timezone=ONDERHOUD_TIMEZONE),
                id="ml_model_training",
                name="ML Model Training",
                replace_existing=True,
            )

            # Schedule retention cleanup (daily at 04:00 AM)
            _sched.add_job(
                self._run_retention_cleanup,
                trigger=CronTrigger(hour=4, minute=0, timezone=ONDERHOUD_TIMEZONE),
                id="retention_cleanup",
                name="Data Retention Cleanup",
                replace_existing=True,
            )

            # Schedule prana budget refill (daily at 00:00, ADR-021). Idempotent reset.
            _sched.add_job(
                self._run_prana_refill,
                trigger=CronTrigger(hour=0, minute=0, timezone=ONDERHOUD_TIMEZONE),
                id="prana_refill",
                name="Prana Budget Daily Refill",
                replace_existing=True,
            )

            # Schedule twin observation cleanup (daily at 03:00 AM)
            _sched.add_job(
                self._run_twin_observation_cleanup,
                trigger=CronTrigger(hour=3, minute=0, timezone=ONDERHOUD_TIMEZONE),
                id="twin_observation_cleanup",
                name="Twin Observation Cleanup",
                replace_existing=True,
            )

            # Schedule twin cost log cleanup (daily at 03:15 AM)
            _sched.add_job(
                self._run_twin_cost_log_cleanup,
                trigger=CronTrigger(hour=3, minute=15, timezone=ONDERHOUD_TIMEZONE),
                id="twin_cost_log_cleanup",
                name="Twin Cost Log Retention Cleanup",
                replace_existing=True,
            )

            # Schedule twin profile aggregation (daily at 02:30 AM)
            _sched.add_job(
                self._run_twin_profile_aggregation,
                trigger=CronTrigger(hour=2, minute=30, timezone=ONDERHOUD_TIMEZONE),
                id="twin_profile_aggregation",
                name="Digital Twin Profile Aggregation",
                replace_existing=True,
            )

            # Schedule stale task cleanup (every hour at :30 -- ADR-007: 1-hour timeout)
            _sched.add_job(
                self._run_stale_task_cleanup,
                trigger=CronTrigger(minute=30, timezone=ONDERHOUD_TIMEZONE),
                id="stale_task_cleanup",
                name="Stale Task Cleanup",
                replace_existing=True,
            )

            # Schedule HITL ticket SLA cleanup (every hour at :15 -- marks past-SLA tickets as expired)
            _sched.add_job(
                self._run_hitl_ticket_cleanup,
                trigger=CronTrigger(minute=15, timezone=ONDERHOUD_TIMEZONE),
                id="hitl_ticket_cleanup",
                name="HITL Ticket SLA Expiry Cleanup",
                replace_existing=True,
            )

            # Debiteuren Keten B: goedgekeurde berichten echt versturen (elke minuut).
            _sched.add_job(
                self._run_verstuur_klare_berichten,
                trigger=CronTrigger(minute="*", timezone=KLANT_TIMEZONE),
                id="verstuur_klare_berichten",
                name="Debiteuren: verstuur klare berichten",
                replace_existing=True,
            )

            # Debiteuren opvolgen: een keer per dag (04:15); escaleert `herinnerd` dossiers na 14
            # dagen. Verstuurt niets.
            _sched.add_job(
                self._run_volg_debiteuren_op,
                trigger=CronTrigger(hour=4, minute=15, timezone=KLANT_TIMEZONE),
                id="volg_debiteuren_op",
                name="Debiteuren opvolgen",
                replace_existing=True,
            )

            # HR-termijnen: een keer per dag (07:00); zet meldingen in de app voor wie hr:read
            # heeft. Signaleert alleen: verandert, wijst en beslist niets.
            _sched.add_job(
                self._run_signaleer_hr_termijnen,
                trigger=CronTrigger(hour=7, minute=0, timezone=KLANT_TIMEZONE),
                id="signaleer_hr_termijnen",
                name="HR-termijnen signaleren",
                replace_existing=True,
            )

            # Bonnen ouder dan 30 dagen opruimen (bonlezer dag 4; besluit Rakesh 2026-10-17: "30 dagen
            # bewaren en zijn daarmee lezer"). Alleen de geuploade bon en zijn metabestand; de actor draait
            # in de worker die het uploadvolume schrijfbaar ziet.
            _sched.add_job(
                self._run_ruim_bonnen_op,
                trigger=CronTrigger(hour=4, minute=30, timezone=ONDERHOUD_TIMEZONE),
                id="ruim_bonnen_op",
                name="Geuploade bonnen na 30 dagen opruimen",
                replace_existing=True,
            )

            # Schedule council decisions cleanup (daily at 03:00 AM)
            _sched.add_job(
                self._run_cleanup_council_decisions,
                trigger=CronTrigger(hour=3, minute=0, timezone=ONDERHOUD_TIMEZONE),
                id="cleanup_council_decisions",
                name="Council Decisions Retention Cleanup",
                replace_existing=True,
            )

            # Schedule agent critiques retention (daily at 03:05 AM UTC -- ADR-036 OP-60).
            # 180 dagen bewaartermijn die tot 2026-08-17 door niets werd uitgevoerd.
            _sched.add_job(
                self._run_cleanup_agent_critiques,
                trigger=CronTrigger(hour=3, minute=5, timezone=ONDERHOUD_TIMEZONE),
                id="cleanup_agent_critiques",
                name="Agent Critiques Retention Cleanup",
                replace_existing=True,
            )

            # Schedule HITL ticket retention (daily at 03:20 AM UTC -- ADR-036 OP-47).
            # `cleanup_expired_hitl_tickets` hierboven MARKEERT tickets als verlopen; dit
            # VERWIJDERT afgehandelde tickets na de bewaartermijn. Tot 2026-08-05 bestond dat
            # verwijderpad niet -- gemeten: geen enkele `delete(HITLTicket)` in src/, en geen
            # art.-17-route die deze tabel raakt.
            _sched.add_job(
                self._run_cleanup_resolved_hitl_tickets,
                trigger=CronTrigger(hour=3, minute=20, timezone=ONDERHOUD_TIMEZONE),
                id="cleanup_resolved_hitl_tickets",
                name="HITL Ticket Retention Cleanup",
                replace_existing=True,
            )

            # Schedule memory purge (daily at 03:40 AM UTC -- AUDIT-004, GDPR art. 17:
            # physically erases soft-deleted memory_items past the grace period)
            _sched.add_job(
                self._run_purge_soft_deleted_memory_items,
                trigger=CronTrigger(hour=3, minute=40, timezone=ONDERHOUD_TIMEZONE),
                id="purge_soft_deleted_memory_items",
                name="Memory Items Soft-Delete Purge",
                replace_existing=True,
            )

            # Ketenverificatie (ADR-036 OP-109). Tot 2026-08-10 stond hier NIETS: de actor
            # bestond, de job had een DEFAULT_SCHEDULE, en toch werd de auditketen nooit
            # automatisch nagerekend -- manipulatie werd alleen opgemerkt als een mens toevallig
            # een admin-endpoint aanriep. Elke versterking van de hash zelf is zinloos zolang
            # niemand kijkt; dit is daarom de stap voor het anker en voor de HMAC.
            #
            # 03:00 conform DEFAULT_SCHEDULE in src/core/jobs/audit_verification.py, dus voor de
            # opruimacties hieronder: eerst vaststellen wat er staat, dan pas verwijderen.
            _sched.add_job(
                self._run_audit_verification,
                trigger=CronTrigger(hour=3, minute=0, timezone=ONDERHOUD_TIMEZONE),
                id="run_audit_verification",
                name="Audit Chain Verification (audit_logs)",
                replace_existing=True,
            )

            # Wekelijkse BagIt-archiefexport van de publieke Levend Monument-collectie
            # (ADR-029 Cat 4, BE-EP-054). Zondag 02:15 UTC: buiten het wisselvenster en voor
            # de dagelijkse opruimacties.
            _sched.add_job(
                self._run_foundation_archive_exports,
                trigger=CronTrigger(
                    day_of_week="sun", hour=2, minute=15, timezone=ONDERHOUD_TIMEZONE
                ),
                id="export_foundation_archives",
                name="Foundation Archive Export (BagIt)",
                replace_existing=True,
            )

            # De raad-keten. Stond niet in OP-109 en is gevonden bij het uitzoeken van
            # OP-118/119/120: dit is het enige pad dat `copilot_hash_chain_breaks_total` bij
            # PERIODIEKE verificatie ophoogt. De alertregel CouncilHashChainBreak bestond dus
            # wel, maar kon alleen vuren op schrijf-tijd-detectie.
            _sched.add_job(
                self._run_check_hash_chain_integrity,
                trigger=CronTrigger(hour=3, minute=10, timezone=ONDERHOUD_TIMEZONE),
                id="check_hash_chain_integrity",
                name="Council Hash Chain Integrity Check",
                replace_existing=True,
            )

            # De logregel leest de tijdzone van de TRIGGER zelf, niet een constante: zo kan het
            # log nooit meer "UTC" zeggen terwijl de job op een andere klok draait.
            for job in _sched.get_jobs():
                logger.info("Scheduled %s: %s (%s)", job.id, job.trigger, job.trigger.timezone)

            logger.info("Task scheduler initialized successfully")
            return True

        except ImportError as e:
            logger.error(
                f"Failed to initialize scheduler - missing dependencies: {e}. "
                "Install with: pip install apscheduler"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {e}", exc_info=True)
            return False

    def _op_job_probleem(self, event: JobEvent) -> None:
        """Luisteraar voor APScheduler-problemen: fouten, gemiste uitvoeringen, instantieoverschrijding.

        `job_id` en `reden` staan als EIGEN logargumenten (niet geinterpoleerd in de tekst) zodat
        een test op `record.args` kan asserteren -- een check op de uitgeschreven string wordt
        waargemaakt door de tekst van de uitzondering zelf (gemeten 2026-09-25).

        Nagemeten (2026-09-26, regie-bevinding):
          EVENT_JOB_ERROR      -> JobExecutionEvent   velden o.a. exception, traceback
          EVENT_JOB_MISSED     -> JobExecutionEvent   exception is None
          EVENT_JOB_MAX_INSTANCES -> JobSubmissionEvent  GEEN exception-veld

        `getattr(event, "exception", None)` vangt het ontbrekende veld op MAX_INSTANCES netjes af.
        De luisteraar zelf gooit niet: APScheduler vangt een gooiende luisteraar af, maar
        een gooiende luisteraar zou dan precies de faalvorm krijgen die hij moet melden.
        """
        from apscheduler.events import (
            EVENT_JOB_ERROR,
            EVENT_JOB_MAX_INSTANCES,
            EVENT_JOB_MISSED,
        )

        _PROBLEEM = {
            EVENT_JOB_ERROR: "fout",
            EVENT_JOB_MISSED: "gemiste uitvoering",
            EVENT_JOB_MAX_INSTANCES: "instantielimiet bereikt",
        }
        job_id = event.job_id
        reden = _PROBLEEM.get(event.code, "onbekend probleem")
        uitzondering = getattr(event, "exception", None)
        if uitzondering is not None:
            logger.error("job-%s: %s", reden, job_id, exc_info=uitzondering)
        else:
            logger.warning("job-%s: %s", reden, job_id)

    async def _run_pack_health_job(self) -> None:
        """Enqueue the pack health aggregation job or raise if enqueuing fails."""
        from src.workers.actors import run_pack_health_aggregation

        run_pack_health_aggregation.send()

    async def _run_daily_maintenance(self) -> None:
        """Enqueue the daily maintenance job or raise if enqueuing fails."""
        from src.workers.actors import run_daily_maintenance

        run_daily_maintenance.send()

    async def _run_ml_model_training(self) -> None:
        """Enqueue the ML model training job or raise if enqueuing fails."""
        from src.workers.actors import run_ml_model_training

        run_ml_model_training.send()

    async def _run_retention_cleanup(self) -> None:
        """Enqueue the data retention cleanup job and the AVG purge planner, or raise.

        De AVG-planner (gebruikers van wie de wistermijn van 30 dagen om is) hoort bij de
        bewaartermijnen en draait dagelijks mee. Bewust GEEN eigen cron-job met een eigen import:
        elke nieuwe importregel in deze klasse telt als +1 Ce voor agent_runtime (DSM-plafond).
        """
        from src.workers.actors import run_avg_purge_vervallen, run_retention_cleanup

        try:
            run_retention_cleanup.send()
        finally:
            # Onafhankelijk van elkaar: een fout bij de ene mag de andere niet overslaan.
            run_avg_purge_vervallen.send()

    async def _run_prana_refill(self) -> None:
        """Enqueue the daily prana refill or raise if enqueuing fails.

        The reset is idempotent, so firing it once per worker is harmless.
        """
        from src.workers.actors import run_prana_refill

        run_prana_refill.send()

    async def _run_twin_observation_cleanup(self) -> None:
        """Enqueue the twin observation cleanup job or raise if enqueuing fails."""
        from src.core.learning.worker import cleanup_expired_observations

        cleanup_expired_observations.send()

    async def _run_twin_cost_log_cleanup(self) -> None:
        """Enqueue the twin cost log retention cleanup job or raise if enqueuing fails."""
        from src.core.learning.worker import twin_cost_log_retention_cleanup

        twin_cost_log_retention_cleanup.send()

    async def _run_twin_profile_aggregation(self) -> None:
        """Enqueue the twin profile aggregation job or raise if enqueuing fails."""
        from src.workers.actors import run_twin_profile_aggregation

        run_twin_profile_aggregation.send()

    async def _run_stale_task_cleanup(self) -> None:
        """Enqueue the stale task cleanup job or raise if enqueuing fails (ADR-007: 1-hour timeout)."""
        from src.workers.actors import cleanup_stale_tasks

        cleanup_stale_tasks.send()

    async def _run_hitl_ticket_cleanup(self) -> None:
        """Enqueue the HITL ticket SLA expiry cleanup job or raise if enqueuing fails."""
        from src.workers.actors import cleanup_expired_hitl_tickets

        cleanup_expired_hitl_tickets.send()

    @staticmethod
    def _governance_cleanup_actors() -> tuple[
        Any, Any, Any  # TODO(TYPE): replace Any with concrete type
    ]:
        """Alle governance-opruimactors uit EEN import-statement (ADR-034 importbudget).

        `tests/architecture/test_dsm006_ar_governance_fan_out.py` telt import-STATEMENTS per
        modulepaar, niet unieke modules. Een tweede `from src.core.governance.retention_cleanup
        import ...` elders in dit bestand tilde agent_runtime->governance van 7 naar 8 en liet die
        guard omvallen. Samenvoegen lost het op zonder de lazy import op te geven -- die is er om
        te voorkomen dat de scheduler bij het laden een governance-afhankelijkheid krijgt.
        """
        from src.core.governance.retention_cleanup import (
            cleanup_agent_critiques,
            cleanup_council_decisions,
            cleanup_resolved_hitl_tickets,
        )

        return cleanup_council_decisions, cleanup_resolved_hitl_tickets, cleanup_agent_critiques

    async def _run_verstuur_klare_berichten(self) -> None:
        """Enqueue het versturen van klare debiteurenberichten or raise if enqueuing fails."""
        from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten

        verstuur_klare_berichten.send()

    async def _run_volg_debiteuren_op(self) -> None:
        """Daily: escalate reminded receivables after 14 days (Keten B dag 3)."""
        from src.core.tasks.debiteuren_tasks import volg_debiteuren_op

        volg_debiteuren_op.send()

    async def _run_signaleer_hr_termijnen(self) -> None:
        """Daily: meldingen voor naderende HR-termijnen (HR-pilot dag 4)."""
        from src.core.tasks.hr_termijn_tasks import signaleer_hr_termijnen

        signaleer_hr_termijnen.send()

    async def _run_ruim_bonnen_op(self) -> None:
        """Daily: geuploade bonnen ouder dan 30 dagen verwijderen (bonlezer dag 4, besluit Rakesh)."""
        from src.core.tasks.bonnen_opruimen import ruim_bonnen_op

        ruim_bonnen_op.send()

    async def _run_cleanup_council_decisions(self) -> None:
        """Enqueue the council decisions cleanup job or raise if enqueuing fails."""
        cleanup_council_decisions, _, _ = self._governance_cleanup_actors()
        cleanup_council_decisions.send()

    async def _run_cleanup_agent_critiques(self) -> None:
        """Enqueue de agent-kritieken-retentie of raise if enqueuing fails (ADR-036 OP-60).

        Deze actor bestond sinds 2026-08-05 met een bewaartermijn van 180 dagen, maar stond
        in geen enkele scheduler-job -- hij draaide dus nooit. Extra misleidend omdat
        `agent_critiques` WEL op de retentie-allowlist staat
        (`retention_cleanup.py:_RETENTION_ALLOWED_TABLES`): wie die lijst leest concludeert
        dat de termijn gehandhaafd wordt. Geborgd door
        `tests/architecture/test_cleanup_actors_are_scheduled.py`.
        """
        _, _, cleanup_agent_critiques = self._governance_cleanup_actors()
        cleanup_agent_critiques.send()

    async def _run_cleanup_resolved_hitl_tickets(self) -> None:
        """Enqueue the HITL ticket retention job or raise if enqueuing fails (ADR-036 OP-47)."""
        _, cleanup_resolved_hitl_tickets, _ = self._governance_cleanup_actors()
        cleanup_resolved_hitl_tickets.send()

    async def _run_purge_soft_deleted_memory_items(self) -> None:
        """Enqueue the memory items soft-delete purge job or raise if enqueuing fails (AUDIT-004)."""
        from src.domains.memory.tasks import purge_soft_deleted_memory_items

        purge_soft_deleted_memory_items.send()

    async def _run_foundation_archive_exports(self) -> None:
        """Zet de wekelijkse archiefexport in de wachtrij of raise (BE-EP-054)."""
        from src.workers.actors import export_foundation_archives

        export_foundation_archives.send()

    async def _run_audit_verification(self) -> None:
        """Zet de ketenverificatie van `audit_logs` in de wachtrij of raise (ADR-036 OP-109)."""
        from src.workers.actors import run_audit_verification

        run_audit_verification.send()

    async def _run_check_hash_chain_integrity(self) -> None:
        """Zet de ketencontrole van `council_decisions` in de wachtrij of raise (ADR-036 OP-109)."""
        from src.core.copilot.audit.integrity_check_actor import (
            check_hash_chain_integrity_actor,
        )

        check_hash_chain_integrity_actor.send()

    def start(self) -> None:
        """Start the scheduler."""
        if self.scheduler and not self._running:
            self.scheduler.start()
            self._running = True
            logger.info("Task scheduler started")
        elif not self.scheduler:
            logger.error("Cannot start scheduler - not initialized")
        else:
            logger.warning("Scheduler already running")

    def shutdown(self) -> None:
        """Shutdown the scheduler gracefully."""
        if self.scheduler and self._running:
            self.scheduler.shutdown(wait=True)
            self._running = False
            logger.info("Task scheduler shutdown complete")
        else:
            logger.warning("Scheduler not running or not initialized")

    def get_scheduled_jobs(
        self,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get list of scheduled jobs.

        Returns:
            List of job info dictionaries
        """
        if not self.scheduler:
            return []

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "trigger": str(job.trigger),
                    "next_run_time": (
                        nrt.isoformat() if (nrt := getattr(job, "next_run_time", None)) else None
                    ),
                }
            )
        return jobs


# Global scheduler instance
_scheduler_instance: TaskScheduler | None = None


async def get_scheduler() -> TaskScheduler | None:
    """
    Get or create the global scheduler instance.

    Returns:
        TaskScheduler instance or None if initialization failed
    """
    global _scheduler_instance

    if _scheduler_instance is None:
        _scheduler_instance = TaskScheduler()
        if not await _scheduler_instance.initialize():
            _scheduler_instance = None
            return None

    return _scheduler_instance


def _eis_een_echte_broker(_actors_module: object = None) -> None:
    """Controleer dat geen enkele actor in src.workers.actors nog op een StubBroker hangt.

    `_bind_the_real_broker()` wisselt de globale broker om, maar actors die eerder zijn
    geregistreerd -- voor de wissel, of in een importvolgorde waarbij de stub al is gezet --
    kunnen nog naar het object wijzen dat ze bij registratie kregen. Deze functie toetst het
    OBJECT (actor.broker is/is not StubBroker), niet de naam, zodat een wrapper-klasse die de
    naam "mock" of "stub" draagt maar geen echte StubBroker is, er niet doorheen glipt.

    Gooit bewust hard: een planner die zijn opdrachten in het niets stuurt is erger dan een
    planner die niet start, want de eerste ziet eruit alsof hij werkt (gemeten: OP-76).

    _actors_module: injecteerbaar voor tests; in productie None (import src.workers.actors).
    Injectie voorkomt dat een test sys.modules moet patchen -- patch.dict(sys.modules) werkt
    niet betrouwbaar als het echte module-object al in sys.modules staat en de import-keten
    hem via de package-attribute ophaalt (gemeten 2026-09-26: test slaagde in isolatie,
    faalde in de volledige suite).

    Mutatiebewijs (2026-09-26, scripts/mutation_harness.py, beide UITGEVOERD):
      P1 voorwaarts  -- aanroep uit start_scheduler() verwijderd: volgorde-test ROOD
                        (verwachtte ["bind", "eis", "get"], zag ["bind", "get"]).
      P2 tegenrichting -- actor.broker is MagicMock (niet StubBroker): detectielogica
                          geeft lege lijst, geen RuntimeError.
    """
    try:
        from dramatiq.brokers.stub import StubBroker
    except ImportError:
        return

    import dramatiq as _dramatiq_module  # noqa: PLC0415

    if _actors_module is None:
        import src.workers.actors as _actors_module  # noqa: PLC0415

    # Globale broker na de bind: als de wissel zelf mislukte, weiger dan direct.
    if isinstance(_dramatiq_module.get_broker(), StubBroker):
        raise RuntimeError(
            "Scheduler geweigerd: de globale dramatiq-broker is nog een StubBroker na "
            "get_redis_broker() -- roep _bind_the_real_broker() aan voor _eis_een_echte_broker()."
        )

    # Individuele actors: een actor die VOOR de bind is geregistreerd heeft nog het oude object.
    stub_gebonden: list[str] = []
    for naam, waarde in vars(_actors_module).items():
        if isinstance(waarde, _dramatiq_module.Actor) and isinstance(waarde.broker, StubBroker):
            stub_gebonden.append(naam)

    if stub_gebonden:
        raise RuntimeError(
            f"Scheduler geweigerd: de volgende actors staan nog op een StubBroker en "
            f"sturen hun berichten in het niets -- "
            f"roep get_redis_broker() aan voor start_scheduler(): {sorted(stub_gebonden)}"
        )


def _bind_the_real_broker() -> None:
    """Zorg dat `.send()` in Redis terechtkomt en niet in een geheugenwachtrij (ADR-036 OP-76).

    **Stand sinds OP-13 (2026-10-21).** De workflowbroker is vanaf het importeren een echte RedisBroker en alle
    actors binden er expliciet aan; deze aanroep is nu een ongevaarlijke vangnetregel. Hieronder de meting van
    toen, die het ontstaan van OP-76 uitlegt.

    **Waarom dit nodig WAS, gemeten en niet beredeneerd.** `src/workers/workflow_worker.py` zette bij
    het IMPORTEREN een `StubBroker` als globale broker, en wisselde hem pas om zodra iemand
    `get_redis_broker()` aanroept. Het scheduler-proces deed dat niet. Gemeten in een proces met
    DATABASE_URL en REDIS_URL gezet:

        globale broker              : StubBroker
        cleanup_expired_hitl_tickets: StubBroker   <- de ENIGE handhaving van de SLA van 4 uur
        cleanup_resolved_hitl_tickets: RedisBroker

    Elke `.send()` op een stub-gebonden actor verdween dus in een wachtrij binnen het
    scheduler-proces zelf, en de planner logde vrolijk "enqueued successfully". Geen foutmelding,
    geen opgeruimde tickets. Dat is dezelfde klasse fout als OP-64: een belofte die niemand nakomt,
    en niets dat afgaat wanneer er NIETS gebeurt.

    Faalt bewust hard: een planner die zijn opdrachten in het niets stuurt is erger dan een planner
    die niet start, want de eerste ziet eruit alsof hij werkt.
    """
    from src.workers.workflow_worker import get_redis_broker

    get_redis_broker()


async def start_scheduler() -> TaskScheduler | None:
    """
    Start the global scheduler.

    Returns:
        Running TaskScheduler instance or None if failed
    """
    if not SCHEDULER_ENABLED:
        logger.info("Scheduler is disabled (SCHEDULER_ENABLED=false)")
        return None

    _bind_the_real_broker()
    _eis_een_echte_broker()

    scheduler = await get_scheduler()
    if scheduler:
        scheduler.start()
    return scheduler


def shutdown_scheduler() -> None:
    """Shutdown the global scheduler."""
    global _scheduler_instance
    if _scheduler_instance:
        _scheduler_instance.shutdown()
        _scheduler_instance = None


# ============================================================================
# CLI for running the scheduler
# ============================================================================

if __name__ == "__main__":
    """
    Run the scheduler as a standalone process.

    Usage:
        python -m src.workers.scheduler

    Environment Variables:
        SCHEDULER_ENABLED: Set to "false" to disable scheduler (default: true)
        SCHEDULER_TIMEZONE: Timezone for scheduling (default: UTC)
        REDIS_URL: Redis connection string for Dramatiq
        DATABASE_URL: PostgreSQL connection string
    """
    import signal

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def main() -> int:
        # Handle shutdown gracefully
        shutdown_event = asyncio.Event()

        def signal_handler(
            signum: int,
            frame: Any,  # TODO(TYPE): replace Any with concrete type
        ) -> None:
            logger.info(f"Received signal {signum}, shutting down...")
            shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Start scheduler
        scheduler = await start_scheduler()
        if not scheduler:
            logger.error("Failed to start scheduler")
            return 1

        # Log scheduled jobs
        jobs = scheduler.get_scheduled_jobs()
        for job in jobs:
            logger.info(f"  - {job['name']} ({job['id']}): {job['trigger']}")

        # Keep running until shutdown signal
        logger.info("Scheduler is running. Press Ctrl+C to stop.")
        await shutdown_event.wait()

        # Shutdown
        shutdown_scheduler()
        return 0

    exit_code = asyncio.run(main())
    exit(exit_code)
