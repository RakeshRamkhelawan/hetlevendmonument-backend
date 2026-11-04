"""OODA-loop subscriber voor InterventionSuggested events.

Orient-fase: analyseer critique-score, publiceer CritiqueScoreLow event op TwinEventBus.
Decide-fase: log interventieaanbeveling (stub).
Act-fase: post-MVP per ADR-025 par. 3.4.
"""

import logging

from src.core.learning.events.event_bus import get_twin_event_bus
from src.core.learning.events.twin_events import CritiqueScoreLow
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

# SP-AGT-008: scores below this threshold trigger Orient-fase event publication.
# Gelijk aan ShadowCEO._CRITIQUE_RISK_THRESHOLD (0.35) -- vroeg-waarschuwingssignaal.
_ORIENT_SCORE_THRESHOLD: float = 0.35


class OODALoopObserver:
    """OODA-loop observer: Orient + Decide fasen voor critique-score events."""

    async def on_intervention_suggested(
        self,
        user_id: int,
        tenant_id: int,
        event_data: dict[str, object],
    ) -> None:
        raw_score = event_data.get("score")
        agent_name = str(event_data.get("agent_name", ""))

        if not isinstance(raw_score, (int, float)):
            return

        score: float = float(raw_score)
        if score < _ORIENT_SCORE_THRESHOLD:
            await self._orient_publish_critique_event(
                user_id=user_id,
                tenant_id=tenant_id,
                agent_name=agent_name,
                score=score,
            )
            self._decide_log_intervention(
                tenant_id=tenant_id,
                agent_name=agent_name,
                score=score,
            )

    async def _orient_publish_critique_event(
        self,
        user_id: int,
        tenant_id: int,
        agent_name: str,
        score: float,
    ) -> None:
        """Orient-fase: publiceer CritiqueScoreLow event op TwinEventBus (best-effort)."""

        async with best_effort("ooda_orient_publish_critique_score_low"):
            bus = get_twin_event_bus()
            await bus.publish(
                CritiqueScoreLow(
                    user_id=str(user_id),
                    tenant_id=tenant_id,
                    agent_name=agent_name,
                    score=score,
                )
            )

    def _decide_log_intervention(
        self,
        tenant_id: int,
        agent_name: str,
        score: float,
    ) -> None:
        """Decide-fase: log interventieaanbeveling."""
        logger.info(
            "ooda_decide_intervention tenant_id=%s agent_name=%s score=%.2f",
            tenant_id,
            agent_name,
            score,
            extra={"tenant_id": tenant_id, "event": "ooda_decide_intervention"},
        )
        # TODO(post-MVP ADR-025 par. 3.4): Act-fase -- stuur corrigerende actie naar agent
