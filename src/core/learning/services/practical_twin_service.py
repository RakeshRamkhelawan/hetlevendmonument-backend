"""
PracticalTwinService -- Hoofd-service die alles samenvoegt.

Verantwoordelijkheden:
1. track_behavior(): delegeert naar UserBehaviorObserver
2. analyze_struggle(): berekent WeightedStruggleScore + suggereert interventie
3. get_profile(): leest het cognitieve profiel van een user

WeightedStruggleScore:
  Factoren:
    - regedit_loops (0.4): herhaalde edits op dezelfde regel
    - rapid_file_switching (0.3): snel wisselen van bestanden
    - delete_heavy_refactoring (0.2): veel deletes in korte tijd
    - error_spike (0.1): fouten in de laatste minuut
  Drempelwaarde: > 0.8 -> interventie nodig

Gebruik:
    service = PracticalTwinService(
        observer=observer,
        llm_provider=mock_provider,
    )
    result = await service.track_behavior(user_id="u1", ...)
    suggestion = await service.analyze_struggle(context={...}, profile={...})
"""

from typing import Any

from loguru import logger

from src.core.learning.events.event_bus import TwinEventBus
from src.core.learning.interfaces.llm_provider import ILLMSuggestionProvider, MockSuggestionProvider
from src.core.learning.observers.user_behavior_observer import UserBehaviorObserver


class WeightedStruggleScore:
    """
    Berekent een gewogen score die aangeeft hoe 'vast' een user zit.

    Interventiegrens: score > 0.8 -> twin suggereert hulp.

    Factoren en gewichten:
        regedit_loops (0.4):             herhaalde edits op dezelfde locatie
        rapid_file_switching (0.3):      snelle bestand-wissels (>= 8 in short window)
        delete_heavy_refactoring (0.2):  veel deletes in 1 minuut (>= 50 regels)
        error_spike (0.1):               fouten in de laatste minuut (>= 5)
    """

    WEIGHTS = {
        "regedit_loops": 0.4,
        "rapid_file_switching": 0.3,
        "delete_heavy_refactoring": 0.2,
        "error_spike": 0.1,
    }
    INTERVENTION_THRESHOLD = 0.8

    # Normalisatiegrenzen (waarboven = factor 1.0)
    _NORMS = {
        "regedit_loops": 10.0,  # 10 herhaalde edits
        "rapid_file_switching": 8.0,  # 8 bestandswissels
        "delete_heavy_refactoring": 50.0,  # 50 verwijderde regels
        "error_spike": 5.0,  # 5 fouten
    }

    @classmethod
    def calculate(cls, context: dict[str, Any]) -> float:  # TODO(TYPE): replace Any with concrete type
        """
        Bereken de struggle score op basis van context.

        Args:
            context: Dict met gedragsindicatoren (output van PrivacyFilter.filter_context)

        Returns:
            Float tussen 0.0 (geen struggle) en 1.0 (maximale struggle)
        """
        score = 0.0

        # Factor 1: regedit loops
        edits = float(context.get("recent_edits_same_line", 0))
        score += cls.WEIGHTS["regedit_loops"] * min(edits / cls._NORMS["regedit_loops"], 1.0)

        # Factor 2: rapid file switching
        switches = float(context.get("recent_file_switches", 0))
        score += cls.WEIGHTS["rapid_file_switching"] * min(
            switches / cls._NORMS["rapid_file_switching"], 1.0
        )

        # Factor 3: delete-heavy refactoring
        deletes = float(context.get("lines_deleted_last_minute", 0))
        score += cls.WEIGHTS["delete_heavy_refactoring"] * min(
            deletes / cls._NORMS["delete_heavy_refactoring"], 1.0
        )

        # Factor 4: error spike
        errors = float(context.get("errors_last_minute", 0))
        score += cls.WEIGHTS["error_spike"] * min(errors / cls._NORMS["error_spike"], 1.0)

        return round(score, 3)

    @classmethod
    def needs_intervention(cls, score: float) -> bool:
        """Geeft True als de score boven de drempelwaarde is."""
        return score > cls.INTERVENTION_THRESHOLD


class PracticalTwinService:
    """
    Facade service voor de Practical Digital Twin.

    Combineert tracking, struggle detection en LLM suggesties.
    """

    def __init__(
        self,
        observer: UserBehaviorObserver,
        llm_provider: ILLMSuggestionProvider | None = None,
        consent_manager: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        cost_tracker: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        event_bus: TwinEventBus | None = None,
    ):
        self._observer = observer
        self._llm = llm_provider or MockSuggestionProvider(response="")
        self._consent = consent_manager
        self._cost = cost_tracker
        self._bus = event_bus

    async def track_behavior(
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
        Track een user gedrags-observatie via de observer pipeline.

        Returns:
            trace_id als succesvol, None als verworpen.
        """
        trace_id = await self._observer.track(
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            behavior_type=behavior_type,
            context=context,
            outcome_metrics=outcome_metrics,
            confidence_score=confidence_score,
        )
        # Observations are batched by the singleton ObservationBatchManager.
        # Background flush loop handles persistence (ADR-025).
        return trace_id

    async def analyze_struggle(
        self,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        user_profile: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        user_id: str | None = None,
        tenant_id: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Analyseer of de user vastloopt en genereer een suggestie indien nodig.

        Returns:
            Dict met:
                - score: float (WeightedStruggleScore)
                - needs_intervention: bool
                - suggestion: str (leeg als geen interventie nodig)
                - reason: str | None (why no intervention)
                - log_id: int | None (suggestion log ID for feedback)
        """
        score = WeightedStruggleScore.calculate(context)
        needs_help = WeightedStruggleScore.needs_intervention(score)

        suggestion = ""
        log_id: int | None = None

        if needs_help:
            # Check ai_interventions consent (ADR-026 S.2)
            effective_user_id = user_id or user_profile.get("user_id", "")
            effective_tenant_id = tenant_id or user_profile.get("tenant_id", 0)
            if self._consent is not None and effective_user_id and effective_tenant_id:
                categories = await self._consent.get_consent_categories(
                    str(effective_user_id), int(effective_tenant_id)
                )
                if not categories.ai_interventions:
                    logger.info(
                        "twin_ai_intervention_blocked_by_consent",
                        user_id=effective_user_id,
                        tenant_id=effective_tenant_id,
                    )
                    return {
                        "score": score,
                        "needs_intervention": False,
                        "suggestion": "",
                        "reason": "user_opted_out_art22",
                        "log_id": None,
                    }

            try:
                suggestion = await self._llm.suggest(context, user_profile)
                logger.debug(
                    "twin_intervention_suggested",
                    score=score,
                    suggestion_length=len(suggestion),
                )

                # Publish event for OODA-loop consumers (ADR-025 S.3.4)
                if suggestion and self._bus is not None:
                    from src.core.learning.events.twin_events import InterventionSuggested

                    await self._bus.publish_async(
                        InterventionSuggested(
                            user_id=str(effective_user_id),
                            tenant_id=int(effective_tenant_id),
                            intervention_type="struggle",
                            message=suggestion,
                            confidence=score,
                        )
                    )

                # Log cost for eval harness and budget tracking (ADR-026 S.1.2.2)
                if self._cost is not None and effective_user_id and effective_tenant_id:
                    try:
                        token_usage = getattr(self._llm, "last_token_usage", None)
                        input_tokens = token_usage.input_tokens if token_usage else 0
                        output_tokens = (
                            token_usage.output_tokens if token_usage else len(suggestion.split())
                        )
                        log = await self._cost.log_suggestion(
                            tenant_id=int(effective_tenant_id),
                            user_id=str(effective_user_id),
                            provider_name=getattr(self._llm, "provider_names", ["Unknown"])[0],
                            suggestion_text=suggestion,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            score=score,
                        )
                        log_id = log.id
                    except Exception as exc:
                        logger.warning(
                            "twin_cost_log_failed",
                            error_type=type(exc).__name__,
                            error=str(exc),
                        )
            except Exception as exc:
                logger.warning(
                    "twin_llm_suggestion_failed",
                    score=score,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                # Geen suggestie maar ook geen crash

        return {
            "score": score,
            "needs_intervention": needs_help,
            "suggestion": suggestion,
            "reason": None,
            "log_id": log_id,
        }

    async def get_profile(
        self,
        user_id: str,
        tenant_id: int,
        db: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Leest het cognitieve profiel van een user uit de database.
        Returns {} als er nog geen profiel bestaat of cross_session_memory consent ontbreekt.
        """
        # Check cross_session_memory consent (ADR-026 S.2, AVG Art. 7)
        if self._consent is not None:
            categories = await self._consent.get_consent_categories(str(user_id), int(tenant_id))
            if not categories.cross_session_memory:
                logger.info(
                    "twin_cross_session_memory_blocked_by_consent",
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                return {}

        from sqlalchemy import select

        from src.core.learning.twin_models import UserCognitiveProfile

        try:
            result = await db.execute(
                select(UserCognitiveProfile).where(
                    UserCognitiveProfile.human_user_id == user_id,
                    UserCognitiveProfile.tenant_id == tenant_id,
                )
            )
            profile = result.scalar_one_or_none()
        except Exception as exc:
            logger.warning(
                "twin_get_profile_failed",
                user_id=user_id,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            return {}

        if profile is None:
            return {}

        profile_data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "coding_style": profile.coding_style or {},
            "work_patterns": profile.work_patterns or {},
            "optimal_help_style": profile.optimal_help_style,
            "confidence_level": profile.confidence_level,
            "observation_count": profile.observation_count,
        }

        # Augment with ContextPackerService snapshot (ADR-025 Task 3.2).
        # Only when TWIN_MEMORY_SYNC_ENABLED=true -- cross_session_memory consent is
        # already verified above (early return {} guards this code path).
        import os

        if os.getenv("TWIN_MEMORY_SYNC_ENABLED", "false").lower() in ("true", "1", "yes"):
            from src.core.utils.best_effort import best_effort

            async with best_effort("twin get_profile memory snapshot"):
                from src.domains.memory.services.context_packer_service import (
                    ContextPackerService,
                )

                packer = ContextPackerService(db=db, tenant_id=tenant_id)
                snapshot = await packer.build(agent_id="twin_service")
                # Only include snapshot when it has content -- avoids empty noise in
                # responses before any memory items exist for twin_service.
                if snapshot.get("estimated_tokens", 0) > 0:
                    profile_data["memory_snapshot"] = {
                        "recent_episodes": [
                            {
                                "content": ep.content[:200],
                                "memory_type": ep.memory_type,
                            }
                            for ep in snapshot.get("recent_episodes", [])
                        ],
                        "top_facts": [
                            {"content": f.content[:200]} for f in snapshot.get("top_facts", [])
                        ],
                        "estimated_tokens": snapshot["estimated_tokens"],
                    }

        return profile_data
