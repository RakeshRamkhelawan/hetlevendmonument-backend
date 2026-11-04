"""
TwinPolicy -- ADR-016 veto-chain integration for Digital Twin suggestions.

Architecture:
    TwinPolicy.evaluate(suggestion, score, context)
        -> PolicyDecision (ALLOW | REVIEW | BLOCK)

The policy delegates high-risk suggestions (score >= REVIEW_THRESHOLD) to
a ShadowCEO veto chain via the IShadowVetoChain protocol.

Security invariants (all verified on every call):
    1. NaN / Inf / out-of-range scores  -> REVIEW  (never ALLOW)
    2. Missing veto chain               -> REVIEW  (fail-safe, not fail-open)
    3. Exception in veto chain          -> REVIEW  (never silently ALLOW)
    4. BLOCK from veto chain            -> BLOCK   (ADR-016 four-level veto)
"""

import math
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from loguru import logger


# -- Thresholds -------------------------------------------------------------

# Scores at or above this value are routed through the veto chain.
REVIEW_THRESHOLD = 0.85


# -- Policy decision ---------------------------------------------------------


class PolicyDecision(str, Enum):
    """Outcome of a TwinPolicy evaluation."""

    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


# -- Veto-chain protocol -----------------------------------------------------


@runtime_checkable
class IShadowVetoChain(Protocol):
    """
    Minimal interface that a veto chain must implement.

    The twin policy depends on this protocol, not on ShadowCEO's concrete
    review_task(TaskData) method.  This decouples the learning domain from
    the ALS enterprise domain and makes the policy unit-testable with a
    simple stub.

    Implementors:
        - ShadowCEOAdapter (wraps ShadowCEO.review_task)
        - Any stub in tests  # TODO(TYPE): replace Any with concrete type
    """

    async def evaluate_twin_suggestion(
        self,
        suggestion: str,
        score: float,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Evaluate whether a suggestion should be blocked.

        Returns:
            True  -- suggestion passes the veto chain (ALLOW or lower risk)
            False -- suggestion is vetoed (BLOCK)
        """
        ...


# -- ShadowCEO adapter --------------------------------------------------------


class ShadowCEOVetoAdapter:
    """
    Adapts ShadowCEO.review_task() to the IShadowVetoChain interface.

    Creates a minimal TaskData from the twin suggestion context so the
    ShadowCEO can perform its standard risk analysis.
    """

    def __init__(self, shadow_ceo: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._ceo = shadow_ceo

    async def evaluate_twin_suggestion(
        self,
        suggestion: str,
        score: float,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        from src.core.shared.interfaces import TaskData

        task = TaskData(
            title="twin_suggestion",
            description=suggestion[:500],
            metadata={"score": score, **{k: str(v)[:200] for k, v in context.items()}},
        )
        try:
            veto = await self._ceo.review_task(task=task, proposed_agent="twin_service")
        except Exception as exc:
            logger.warning(
                "shadow_ceo_adapter_review_failed",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            # Fail-secure: ShadowCEO unavailable -> block the suggestion.
            # High-risk suggestions (score >= REVIEW_THRESHOLD) must not slip
            # through when the veto chain is down (H-4 fix).
            return False

        if veto is None:
            return True  # No veto raised -- ALLOW

        from src.core.als.enterprise.shadow.shadow_ceo import RiskLevel

        if veto.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            logger.info(
                "shadow_ceo_vetoed_twin_suggestion",
                risk_level=veto.risk_level.name,
                reason=veto.veto_reason,
            )
            return False  # Vetoed -> BLOCK

        return True  # Acceptable risk -> ALLOW


# -- Main policy class --------------------------------------------------------


class TwinPolicy:
    """
    Evaluate a twin suggestion against the ADR-016 veto chain.

    Args:
        veto_chain: Optional IShadowVetoChain implementation.
                    None -> every high-risk suggestion becomes REVIEW
                    (fail-safe: we never ALLOW without a chain in place).
    """

    def __init__(self, veto_chain: IShadowVetoChain | None = None) -> None:
        self._chain = veto_chain

    async def evaluate(
        self,
        suggestion: str,
        score: float,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[PolicyDecision, str]:
        """
        Evaluate *suggestion* and return (decision, suggestion).

        The returned suggestion may be the original or empty string if blocked.

        Args:
            suggestion: LLM-generated text.
            score:      WeightedStruggleScore (0.0 - 1.0).
            context:    Behaviour context dict passed to the LLM.

        Returns:
            (PolicyDecision, text_to_show)
        """
        # -- Guard: invalid score ---------------------------------------------
        if not math.isfinite(score) or score < 0.0 or score > 1.0:
            logger.warning("twin_policy_invalid_score", score=score)
            return PolicyDecision.REVIEW, suggestion

        # -- Low-risk: below threshold -> immediate ALLOW ----------------------
        if score < REVIEW_THRESHOLD:
            return PolicyDecision.ALLOW, suggestion

        # -- High-risk: route through veto chain ------------------------------
        if self._chain is None:
            logger.info(
                "twin_policy_no_veto_chain",
                score=score,
                note="returning REVIEW (fail-safe)",
            )
            return PolicyDecision.REVIEW, suggestion

        try:
            passes = await self._chain.evaluate_twin_suggestion(suggestion, score, context)
        except Exception as exc:
            logger.warning(
                "twin_policy_veto_chain_error",
                error_type=type(exc).__name__,
                error=str(exc),
                score=score,
            )
            # Fail-safe: exception in veto chain -> REVIEW, never ALLOW
            return PolicyDecision.REVIEW, suggestion

        if not passes:
            logger.info("twin_policy_blocked", score=score)
            return PolicyDecision.BLOCK, ""

        return PolicyDecision.ALLOW, suggestion
