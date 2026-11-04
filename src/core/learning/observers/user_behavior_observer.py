"""
UserBehaviorObserver -- Hoofd-orchestrator voor het bijhouden van user gedrag.

Pipeline per track() aanroep:
1. Feature flag check (twin.enabled)
2. Consent check (is tracking enabled voor deze user?)
3. Rate limiting (is het rate limit niet overschreden?)
4. Privacy filter (anonimiseer de context)
5. Voeg toe aan batch buffer
6. Publiceer event op de TwinEventBus

Fail-safe: als een stap mislukt, wordt de observatie verworpen (nooit crash).
Privacy-first: als de privacy filter mislukt -> reject (fail-secure).

Gebruik:
    observer = UserBehaviorObserver(
        batch_manager=manager,
        consent_manager=consent_mgr,
        rate_limiter=rate_limiter,
        event_bus=event_bus,
    )
    await observer.track(
        user_id="user@example.com",
        tenant_id=1,
        session_id="sess_abc",
        behavior_type="file_edit",
        context={"file_path": "/home/user/app.py", "edit_count": 3},
    )
"""

import uuid
from typing import Any, Optional

from loguru import logger

from src.core.learning.batching.batch_manager import ObservationBatchManager, PendingObservation
from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.events.event_bus import TwinEventBus
from src.core.learning.events.twin_events import UserBehaviorTracked
from src.core.learning.privacy.privacy_filter import PrivacyFilter
from src.core.learning.rate_limiting.redis_rate_limiter import RedisRateLimiter
from src.core.services.feature_flags import is_feature_enabled


class UserBehaviorObserver:
    """
    Observeert user gedrag en slaat geanonimiseerde observaties op.

    De observer is de enige entry-point voor het tracken van gedrag.
    """

    def __init__(
        self,
        batch_manager: ObservationBatchManager,
        consent_manager: TwinConsentManager,
        rate_limiter: RedisRateLimiter,
        event_bus: TwinEventBus | None = None,
    ):
        self._batch = batch_manager
        self._consent = consent_manager
        self._rate = rate_limiter
        self._bus = event_bus

    async def track(
        self,
        user_id: str,
        tenant_id: int,
        session_id: str,
        behavior_type: str,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        outcome_metrics: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        confidence_score: float = 1.0,
    ) -> str | None:
        """
        Track een user gedrags-observatie.

        Returns:
            trace_id als de observatie is opgeslagen,
            None als de observatie is verworpen (consent, rate limit, etc.)
        """
        trace_id = str(uuid.uuid4())[:8]
        context = context or {}
        outcome_metrics = outcome_metrics or {}

        try:
            # Stap 1: Feature flag check
            if not is_feature_enabled("twin.enabled"):
                logger.debug("twin_disabled_by_feature_flag", trace_id=trace_id)
                return None

            # Stap 2: Consent check
            tracking_enabled = await self._consent.is_tracking_enabled(user_id, tenant_id)
            if not tracking_enabled:
                logger.debug(
                    "twin_tracking_disabled_by_consent",
                    user_id=user_id,
                    trace_id=trace_id,
                )
                return None

            # Stap 3: Rate limiting
            allowed = await self._rate.is_allowed(user_id, behavior_type)
            if not allowed:
                logger.debug(
                    "twin_rate_limit_exceeded",
                    user_id=user_id,
                    behavior_type=behavior_type,
                    trace_id=trace_id,
                )
                return None

            # Stap 4: Privacy filter (fail-secure: reject bij fout)
            try:
                filtered_context = PrivacyFilter.filter_context(context)
                filtered_metrics = PrivacyFilter.filter_context(outcome_metrics)
                anon_user_id = PrivacyFilter.hash_user_id(user_id, tenant_id)
            except Exception as exc:
                logger.error(
                    "twin_privacy_filter_failed_reject",
                    user_id=user_id,
                    trace_id=trace_id,
                    error=str(exc),
                )
                return None  # fail-secure: geen ruwe data opslaan

            # Stap 5: Voeg toe aan batch
            observation = PendingObservation(
                human_user_id=anon_user_id,
                tenant_id=tenant_id,
                session_id=session_id,
                behavior_type=behavior_type,
                context=filtered_context,
                outcome_metrics=filtered_metrics,
                confidence_score=confidence_score,
                trace_id=trace_id,
            )
            await self._batch.add(observation)

            # Stap 6: Publiceer event
            if self._bus is not None:
                event = UserBehaviorTracked(
                    user_id=anon_user_id,
                    tenant_id=tenant_id,
                    behavior_type=behavior_type,
                    context=filtered_context,
                    trace_id=trace_id,
                )
                await self._bus.publish_async(event)

            logger.debug(
                "twin_observation_tracked",
                user_id=anon_user_id,
                behavior_type=behavior_type,
                tenant_id=tenant_id,
                trace_id=trace_id,
            )
            return trace_id

        except Exception as exc:
            # Uiterste vangnet -- de observer mag NOOIT de hoofdapp laten crashen
            logger.error(
                "twin_observer_unexpected_error",
                user_id=user_id,
                behavior_type=behavior_type,
                trace_id=trace_id,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            return None
