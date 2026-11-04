"""ObservationBatchManager -- Batcht observaties voor efficiente DB-writes.

Strategie:
- Buffer observaties in memory
- Flush op: batch_size (100), time_window (30s), of oud buffer (60s max age)
- Single INSERT met meerdere rows
- Fail-safe: bij flush-failure retries 3x (exponential backoff), daarna verwerpt
- Singleton: gedeelde instantie across alle requests

Gebruik:
    manager = await get_batch_manager()
    await manager.add(PendingObservation(...))
    # Manager wordt gestart bij app startup en gestopt bij shutdown
"""

import asyncio
import os
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

# Imported at module level so tests can patch these names on this module.
# The actual code paths that use them are guarded by TWIN_MEMORY_SYNC_ENABLED.
from src.core.learning.consent.consent_manager import TwinConsentManager
from src.domains.memory.schemas import MemoryItemWrite
from src.domains.memory.services.memory_write_service import MemoryWriteService


@dataclass
class PendingObservation:
    """Een observation in de batch buffer."""

    human_user_id: str
    tenant_id: int
    session_id: str
    behavior_type: str
    context: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    outcome_metrics: dict[str, Any] = field(
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    confidence_score: float = 1.0
    timestamp: float = field(default_factory=time.time)
    trace_id: str = ""


# Type alias voor de inject-bare persist functie
PersistFn = Callable[
    [list[PendingObservation]],
    Coroutine[Any, Any, None],  # TODO(TYPE): replace Any with concrete type
]  # TODO(TYPE): replace Any with concrete type


class ObservationBatchManager:
    """Batch observations voor efficiente database writes.

    De `persist_fn` is dependency-injected zodat de BatchManager zelf
    geen directe DB-koppeling heeft (testbaar zonder DB).

    Thread-safe: `add()` is beschermd door een asyncio.Lock zodat
    meerdere requests tegelijkertijd observaties kunnen toevoegen.
    """

    _MAX_RETRY_ATTEMPTS = 3
    _RETRY_BASE_DELAY = 0.5  # seconds

    def __init__(
        self,
        persist_fn: PersistFn | None = None,
        batch_size: int = 100,
        flush_interval_seconds: float = 30.0,
        max_buffer_age_seconds: float = 60.0,
    ):
        self._persist_fn = persist_fn
        self.batch_size = batch_size
        self.flush_interval = flush_interval_seconds
        self.max_buffer_age = max_buffer_age_seconds

        self._buffer: list[PendingObservation] = []
        self._last_flush: float = time.time()
        self._flush_lock = asyncio.Lock()
        self._add_lock = asyncio.Lock()
        self._running: bool = False
        self._flush_task: asyncio.Task[Any] | None = (  # TODO(TYPE): replace Any with concrete type
            None  # TODO(TYPE): replace Any with concrete type
        )

    # --- Lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        """Start de background flush loop."""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(
            "batch_manager_started",
            batch_size=self.batch_size,
            flush_interval=self.flush_interval,
        )

    async def stop(self) -> None:
        """Stop de loop en flush resterende observaties."""
        self._running = False
        if self._flush_task:
            try:
                self._flush_task.cancel()
                await self._flush_task
            except asyncio.CancelledError:
                pass
            except RuntimeError as e:
                if "Event loop is closed" not in str(e):
                    raise
                logger.debug("batch_manager_stop_after_loop_close", error=str(e))

        await self.flush()
        logger.info("batch_manager_stopped", remaining_flushed=len(self._buffer))

    # --- Public API -----------------------------------------------------------

    async def add(self, observation: PendingObservation) -> bool:
        """Voeg observatie toe aan de buffer (async-safe).

        Returns:
            True als succesvol toegevoegd.
        """
        async with self._add_lock:
            self._buffer.append(observation)
            buffer_len = len(self._buffer)
            should_flush = (
                buffer_len >= self.batch_size
                or time.time() - self._last_flush >= self.flush_interval
            )

        if should_flush:
            # Fire-and-forget -- non-blocking
            asyncio.create_task(self.flush())

        return True

    _MAX_BUFFER_SIZE = 1000  # Hard cap to prevent OOM on persistent DB failure

    async def flush(self) -> None:
        """Flush buffer naar database met retry logica."""
        async with self._flush_lock:
            if not self._buffer:
                return

            batch = self._buffer.copy()
            self._buffer.clear()

            success = await self._persist_with_retry(batch)
            if not success:
                # Fail-safe: alleen terugzetten als buffer het aankan
                if len(batch) + len(self._buffer) <= self.batch_size * 2 and (
                    len(batch) + len(self._buffer) <= self._MAX_BUFFER_SIZE
                ):
                    self._buffer.extend(batch)
                    logger.warning(
                        "batch_returned_to_buffer",
                        count=len(batch),
                        total_buffer=len(self._buffer),
                    )
                else:
                    logger.critical(
                        "batch_manager_buffer_overflow",
                        dropped_count=len(batch),
                        buffer_size=len(self._buffer),
                    )

    @property
    def buffer_size(self) -> int:
        """Huidige grootte van de buffer (voor monitoring)."""
        return len(self._buffer)

    # --- Internals ------------------------------------------------------------

    async def _persist_with_retry(self, batch: list[PendingObservation]) -> bool:
        """Probeer batch op te slaan met exponential backoff.

        Returns:
            True als opslaan gelukt is, False na alle pogingen.
        """
        if self._persist_fn is None:
            logger.debug("batch_manager_no_persist_fn", count=len(batch))
            return True  # Geen DB geconfigureerd (bijv. in tests)

        for attempt in range(self._MAX_RETRY_ATTEMPTS):
            try:
                await self._persist_fn(batch)
                self._last_flush = time.time()
                logger.debug(
                    "batch_flushed",
                    count=len(batch),
                    attempt=attempt + 1,
                )
                return True
            except Exception as exc:
                delay = self._RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    "batch_flush_failed",
                    attempt=attempt + 1,
                    max_attempts=self._MAX_RETRY_ATTEMPTS,
                    error_type=type(exc).__name__,
                    error=str(exc),
                    exc_info=True,
                    retry_in_seconds=delay,
                )
                if attempt < self._MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(delay)

        logger.error(
            "batch_flush_exhausted_retries",
            count=len(batch),
            max_attempts=self._MAX_RETRY_ATTEMPTS,
        )
        return False

    async def _flush_loop(self) -> None:
        """Background loop voor periodieke flush."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)

                if self._buffer:
                    # Force flush als oudste observatie te oud is
                    oldest = min(obs.timestamp for obs in self._buffer)
                    if time.time() - oldest > self.max_buffer_age:
                        await self.flush()
                    elif len(self._buffer) >= self.batch_size:
                        await self.flush()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "flush_loop_error",
                    error_type=type(exc).__name__,
                    error=str(exc),
                    exc_info=True,
                )


# Module-level singleton instance
_batch_manager_instance: ObservationBatchManager | None = None


async def get_batch_manager(
    persist_fn: PersistFn | None = None,
) -> ObservationBatchManager:
    """Return the singleton ObservationBatchManager instance.

    Lazy-initialized: created on first call. If no persist_fn is provided,
    a default function using get_db_session() is used.
    """
    global _batch_manager_instance
    if _batch_manager_instance is None:
        if persist_fn is None:
            persist_fn = _default_persist_fn
        _batch_manager_instance = ObservationBatchManager(persist_fn=persist_fn)
        await _batch_manager_instance.start()
    return _batch_manager_instance


async def shutdown_batch_manager() -> None:
    """Shutdown the singleton ObservationBatchManager."""
    global _batch_manager_instance
    if _batch_manager_instance is not None:
        await _batch_manager_instance.stop()
        _batch_manager_instance = None
        logger.info("batch_manager_shutdown_complete")


def reset_batch_manager() -> None:
    """Reset the singleton instance (useful for tests)."""
    global _batch_manager_instance
    _batch_manager_instance = None


async def _default_persist_fn(batch: list[PendingObservation]) -> None:
    """Default persistence function using a fresh DB session per flush."""
    from src.core.database.session import get_db_session
    from src.core.learning.repositories.observation_repository import (
        insert_observation_batch,
    )

    async with get_db_session() as db:
        await insert_observation_batch(db, batch)
        await db.commit()

    # Memory sync: disabled by default -- enable with TWIN_MEMORY_SYNC_ENABLED=true.
    # Rollback: set TWIN_MEMORY_SYNC_ENABLED=false to skip this path entirely.
    if os.getenv("TWIN_MEMORY_SYNC_ENABLED", "false").lower() in ("true", "1", "yes"):
        await _sync_observations_to_memory(batch)


async def _sync_observations_to_memory(batch: list[PendingObservation]) -> None:
    """Write qualifying observations to MemoryWriteService (ADR-025 Task 3.2).

    Only observations where the user has consented to both behavior_tracking
    AND cross_session_memory are forwarded. Uses one DB session per unique
    (user_id, tenant_id) group to minimize connection overhead.

    NOTE: GDPR gap -- MemoryItems written here have user_id=None because
    PendingObservation carries only the pseudonymous hashed user_id, not the
    DB integer FK. These items will NOT be reached by user-scoped cascade
    delete on users.id. A follow-up task must add a MemoryItem soft-delete
    by-user path or surface the real user_id integer in PendingObservation.
    Tracked as a known gap in the sprint retrospective.
    """
    import json
    from collections import defaultdict

    from sqlalchemy import text

    from src.core.database.database import db_manager
    from src.core.utils.best_effort import best_effort

    if db_manager.async_session_maker is None:
        logger.warning("twin_memory_sync_skipped: db_manager not initialized")
        return

    # Group by (user_id, tenant_id) -- one consent check per user group,
    # not per observation, to limit DB connection overhead.
    user_batches: dict[tuple[str, int], list[PendingObservation]] = defaultdict(list)
    for obs in batch:
        user_batches[(obs.human_user_id, obs.tenant_id)].append(obs)

    for (user_id, tenant_id), obs_list in user_batches.items():
        async with best_effort(f"twin memory sync tenant={tenant_id} user={user_id[:8]}"):
            async with db_manager.async_session_maker() as db:
                safe_tid = int(tenant_id)
                await db.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(safe_tid)})

                consent_mgr = TwinConsentManager(db=db)
                categories = await consent_mgr.get_consent_categories(user_id, tenant_id)
                if not (categories.behavior_tracking and categories.cross_session_memory):
                    continue  # no consent -- exit best_effort cleanly, next group

                svc = MemoryWriteService(db=db, tenant_id=tenant_id)
                for obs in obs_list:
                    content = (
                        f"behavior:{obs.behavior_type} session:{obs.session_id[:12]} "
                        f"context:{json.dumps(obs.context, default=str)[:200]}"
                    )
                    payload = MemoryItemWrite(
                        content=content,
                        memory_type="episodic",
                        source_type="workflow",
                        agent_id="twin_service",
                        privacy_scope="tenant",
                        confidence=obs.confidence_score,
                    )
                    await svc.write(payload, auto_accept=True)

                await db.commit()
                logger.info(
                    "twin_memory_sync_written",
                    tenant_id=tenant_id,
                    observation_count=len(obs_list),
                )
