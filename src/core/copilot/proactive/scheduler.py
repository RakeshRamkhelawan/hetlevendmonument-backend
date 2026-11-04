"""
ProactiveScheduler - runs proactive monitors per tenant on intervals.

Uses APScheduler AsyncIOScheduler with IntervalTrigger.
Per-tenant sequential execution with error isolation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.services.noodstop_toegang import klant_staat_stil

logger = logging.getLogger(__name__)


class ProactiveScheduler:
    """Schedules and runs proactive monitors per tenant."""

    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        tenant_repo: Any,  # TODO(TYPE): replace Any with concrete type
        monitors: list[ProactiveMonitor],
    ) -> None:
        self._scheduler = scheduler
        self._tenant_repo = tenant_repo
        self._monitors = monitors

    def start(self) -> None:
        for monitor in self._monitors:
            # Skip event-driven monitors -- IntervalTrigger(seconds=0) crashes
            # with ValueError. Event-driven monitors subscribe in __init__ to
            # the event-bus and do NOT belong to the scheduler.
            if monitor.interval_seconds <= 0:
                logger.info(
                    "skipping event-driven monitor %s (interval_seconds=%d)",
                    monitor.name,
                    monitor.interval_seconds,
                )
                continue
            self._scheduler.add_job(
                self._run_for_all_tenants,
                trigger=IntervalTrigger(seconds=monitor.interval_seconds),
                args=[monitor],
                id=f"monitor:{monitor.name}",
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        self._scheduler.start()

    def shutdown(self, wait: bool = True) -> None:
        self._scheduler.shutdown(wait=wait)

    async def _run_for_all_tenants(self, monitor: ProactiveMonitor) -> None:
        active_tenants = await self._tenant_repo.list_active_ids()
        for tenant_id in active_tenants:
            # NOODSTOP PER KLANT (ADR-036 OP-03): deze autonome trigger is een deur -- een monitor
            # begint uit zichzelf en legt voorstellen aan de Council voor. Een stilgezette klant
            # wordt overgeslagen (fail-closed: ook als de stand niet te lezen is). De Council
            # weigert zelf ook, maar zo draait de detectie niet eens.
            # Uitzondering (besluit B ronde 2): een compliance-monitor draait DOOR voor een
            # stilgezette klant (`blijft_draaien_bij_noodstop`, reden bij de klasse). Alleen een
            # expliciete True telt, zodat een onbekende monitor standaard overgeslagen wordt.
            if monitor.blijft_draaien_bij_noodstop is not True and await klant_staat_stil(
                tenant_id
            ):
                logger.warning(
                    "monitor %s overgeslagen voor klant %s (noodstop)",
                    monitor.name,
                    tenant_id,
                )
                continue
            try:
                signals = await asyncio.wait_for(
                    monitor.detect(tenant_id),
                    timeout=monitor.interval_seconds * 0.8,
                )
                for signal in signals:
                    try:
                        await monitor.propose_to_council(signal)
                    except Exception as exc:
                        logger.error(
                            "Failed to propose signal %s to council",
                            signal.signal_id,
                            exc_info=True,
                            extra={"tenant_id": tenant_id, "monitor": monitor.name},
                        )
            except Exception as exc:
                logger.error(
                    "monitor %s failed for tenant %d: %s: %s",
                    monitor.name,
                    tenant_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                    extra={"tenant_id": tenant_id, "monitor": monitor.name},
                )
