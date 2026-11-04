"""
Guna Router - Hybrid Multi-Layer Routing

Implements the Vedische Guna architecture:
- Tamasic (Layer 2): Deterministic, fast, low prana
- Rajasic (Layer 3): Semantic, adaptive, medium prana
- Sattvic (Layer 4): Meta-learning, strategic, high prana
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.als.enterprise.departments.deterministic_router import DeterministicRouter
from src.core.semantic_router.embedders.ollama_embedder import OllamaEmbedder
from src.core.semantic_router.router import RoutingDecision, SanskritiSemanticRouter

logger = logging.getLogger(__name__)


@dataclass
class GunaRoutingResult:
    """Complete routing result with all metadata."""

    department: Department | None
    guna_used: str  # tamasic, rajasic, sattvic
    confidence: float
    prana_cost: int
    reasoning: str
    fallback_used: bool = False


class GunaRouter:
    """
    Master router implementing the Three Guna architecture.

    Routing Strategy:
    1. Try Tamasic first (fast, cheap, reliable for known patterns)
    2. If low confidence / no match -> Rajasic (semantic understanding)
    3. If still uncertain -> Sattvic (meta-learning / escalation)

    Prana Costs:
    - Tamasic: 5-10 (minimal)
    - Rajasic: 25-50 (embedding + vector search)
    - Sattvic: 100+ (LLM reasoning)
    """

    PRANA_COSTS = {
        "tamasic": 5,
        "rajasic": 25,
        "sattvic": 100,
    }

    def __init__(
        self,
        tenant_id: int,
        deterministic_router: DeterministicRouter,
        semantic_router: SanskritiSemanticRouter,
        tamasic_threshold: float = 0.8,  # Min confidence for Tamasic
        rajasic_threshold: float = 0.75,  # Min confidence for Rajasic
    ) -> None:
        self.tenant_id = tenant_id
        self.tamasic = deterministic_router
        self.rajasic = semantic_router
        self.sattvic = None  # Future: ChiefOrchestrator

        self.tamasic_threshold = tamasic_threshold
        self.rajasic_threshold = rajasic_threshold

        self._stats = {
            "tamasic_hits": 0,
            "rajasic_hits": 0,
            "sattvic_hits": 0,
            "fallbacks": 0,
        }

        logger.info(
            f"GunaRouter initialized (tenant={tenant_id}, "
            f"tamasic_threshold={tamasic_threshold}, "
            f"rajasic_threshold={rajasic_threshold})"
        )

    async def route(
        self,
        task: str,
        task_description: str = "",
        available_prana: dict[Department, int] | None = None,
        force_guna: str | None = None,  # For testing/debugging
    ) -> GunaRoutingResult:
        """
        Route task using multi-layer Guna architecture.

        Args:
            task: Task name/type
            task_description: Additional context
            available_prana: Current prana budget per department
            force_guna: Force specific guna (for testing)

        Returns:
            GunaRoutingResult with department and metadata
        """
        # Normalize input
        full_query = f"{task} {task_description}".strip()

        # For testing: allow forcing a specific guna
        if force_guna:
            return await self._force_route(force_guna, full_query, available_prana)

        # =========================================================================
        # LAYER 2: TAMASIC (Deterministic)
        # Fast, cheap, reliable - perfect for known patterns
        # =========================================================================
        if self._can_use_tamasic(available_prana):
            tamasic_result = self.tamasic.route(task, task_description, available_prana)

            if tamasic_result:
                # Check if this is a "high confidence" Tamasic match
                if self._is_high_confidence_tamasic(task):
                    self._stats["tamasic_hits"] += 1
                    logger.debug(f"[U+0001F7E4] Tamasic route: {task[:30]}... -> {tamasic_result.value}")

                    return GunaRoutingResult(
                        department=tamasic_result,
                        guna_used="tamasic",
                        confidence=0.95,  # High confidence for exact matches
                        prana_cost=self.PRANA_COSTS["tamasic"],
                        reasoning="Exact pattern match in deterministic router",
                        fallback_used=False,
                    )

        # =========================================================================
        # LAYER 3: RAJASIC (Semantic)
        # Context-aware, adaptive - for ambiguous or new patterns
        # =========================================================================
        if self._can_use_rajasic(available_prana):
            rajasic_decision = await self.rajasic.route(task, task_description, available_prana)

            if rajasic_decision.is_confident(self.rajasic_threshold):
                self._stats["rajasic_hits"] += 1

                return GunaRoutingResult(
                    department=rajasic_decision.department,
                    guna_used="rajasic",
                    confidence=rajasic_decision.confidence,
                    prana_cost=self.PRANA_COSTS["rajasic"],
                    reasoning=(
                        f"Semantic similarity match (top: {rajasic_decision.similar_routes[0]['utterance'][:50]}..."
                        if rajasic_decision.similar_routes
                        else "Semantic match"
                    ),
                    fallback_used=False,
                )

            # Low confidence Rajasic result - store for potential Sattvic
            low_confidence_result = rajasic_decision
        else:
            low_confidence_result = None

        # =========================================================================
        # LAYER 4: SATTWIC (Meta-Learning)
        # Strategic, exception handling - for complex cases
        # =========================================================================
        if self._can_use_sattvic(available_prana) and self.sattvic:
            self._stats["sattvic_hits"] += 1
            # Future: Call ChiefOrchestrator for strategic decision
            # For now, escalate to human or use best guess

            # If we have a low-confidence Rajasic result, use it with warning
            if low_confidence_result and low_confidence_result.department:
                logger.warning(
                    f"[U+26AA] Sattvic escalation: Using low-confidence Rajasic result "
                    f"for '{task[:30]}...'"
                )
                return GunaRoutingResult(
                    department=low_confidence_result.department,
                    guna_used="sattvic",
                    confidence=low_confidence_result.confidence,
                    prana_cost=self.PRANA_COSTS["sattvic"],
                    reasoning="Escalated: Low confidence in lower layers",
                    fallback_used=True,
                )

        # =========================================================================
        # FALLBACK: Best effort
        # Use whatever we have, even if uncertain
        # =========================================================================
        self._stats["fallbacks"] += 1

        # Priority: Tamasic > Rajasic > None
        fallback_dept = None
        fallback_guna = "none"

        if self.tamasic.route(task, task_description):
            fallback_dept = self.tamasic.route(task, task_description)
            fallback_guna = "tamasic (fallback)"
        elif low_confidence_result and low_confidence_result.department:
            fallback_dept = low_confidence_result.department
            fallback_guna = "rajasic (fallback)"

        if fallback_dept:
            logger.warning(
                f"[WARN] Fallback routing: '{task[:30]}...' -> {fallback_dept.value} "
                f"({fallback_guna})"
            )
            return GunaRoutingResult(
                department=fallback_dept,
                guna_used=fallback_guna,
                confidence=0.3,  # Low confidence for fallback
                prana_cost=self.PRANA_COSTS["tamasic"],
                reasoning="Fallback: No confident match in any layer",
                fallback_used=True,
            )

        # Complete failure - no route found
        logger.error(f"[FAIL] No route found for: {task[:50]}...")
        return GunaRoutingResult(
            department=None,
            guna_used="none",
            confidence=0.0,
            prana_cost=0,
            reasoning="No matching route found in any layer",
            fallback_used=True,
        )

    async def report_outcome(
        self,
        task: str,
        predicted_department: Department,
        actual_department: Department,
        guna_used: str,
        success: bool,
    ) -> None:
        """
        Report routing outcome for learning.

        This feedback loop improves future routing decisions.
        """
        was_correct = predicted_department == actual_department

        # Log the outcome
        if was_correct:
            logger.info(f"[OK] Correct route: {task[:40]}... -> {actual_department.value}")
        else:
            logger.warning(
                f"[FAIL] Wrong route: {task[:40]}... "
                f"predicted={predicted_department.value}, "
                f"actual={actual_department.value}"
            )

        # Update appropriate layer
        if guna_used in ["rajasic", "sattvic"]:
            # Semantic router learns from mistakes
            await self.rajasic.learn(
                task=task,
                correct_department=actual_department,
                was_successful=was_correct,
            )

        # Future: Update Tamasic patterns if frequently wrong
        # Future: Sattvic meta-learning

    def _can_use_tamasic(self, available_prana: dict[Department, int] | None) -> bool:
        """Check if we have enough prana for Tamasic routing."""
        if not available_prana:
            return True
        # Tamasic needs minimal prana (any department can afford it)
        return any(prana >= self.PRANA_COSTS["tamasic"] for prana in available_prana.values())

    def _can_use_rajasic(self, available_prana: dict[Department, int] | None) -> bool:
        """Check if we have enough prana for Rajasic routing."""
        if not available_prana:
            return True
        return any(prana >= self.PRANA_COSTS["rajasic"] for prana in available_prana.values())

    def _can_use_sattvic(self, available_prana: dict[Department, int] | None) -> bool:
        """Check if we have enough prana for Sattvic routing."""
        if not available_prana:
            return True
        return any(prana >= self.PRANA_COSTS["sattvic"] for prana in available_prana.values())

    def _is_high_confidence_tamasic(self, task: str) -> bool:
        """
        Determine if a Tamasic match is high confidence.

        Simple heuristic: exact keyword matches are high confidence.
        """
        # For now, all Tamasic matches are considered high confidence
        # In future, could check pattern specificity
        return True

    async def _force_route(
        self,
        guna: str,
        full_query: str,
        available_prana: dict[Department, int] | None,
    ) -> GunaRoutingResult:
        """Force routing through specific guna (for testing)."""
        if guna == "tamasic":
            result = self.tamasic.route(full_query)
            return GunaRoutingResult(
                department=result,
                guna_used="tamasic (forced)",
                confidence=0.95 if result else 0.0,
                prana_cost=self.PRANA_COSTS["tamasic"],
                reasoning="Forced Tamasic routing",
                fallback_used=False,
            )
        elif guna == "rajasic":
            decision = await self.rajasic.route(full_query, "", available_prana)
            return GunaRoutingResult(
                department=decision.department,
                guna_used="rajasic (forced)",
                confidence=decision.confidence,
                prana_cost=self.PRANA_COSTS["rajasic"],
                reasoning="Forced Rajasic routing",
                fallback_used=False,
            )
        else:
            return await self.route(full_query, "", available_prana)

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get routing statistics."""
        total = sum(self._stats.values())

        return {
            **self._stats,
            "total_routes": total,
            "tamasic_percentage": (self._stats["tamasic_hits"] / total * 100) if total > 0 else 0,
            "rajasic_percentage": (self._stats["rajasic_hits"] / total * 100) if total > 0 else 0,
            "sattvic_percentage": (self._stats["sattvic_hits"] / total * 100) if total > 0 else 0,
            "fallback_percentage": (self._stats["fallbacks"] / total * 100) if total > 0 else 0,
        }


# Factory function for easy creation
async def create_guna_router(
    tenant_id: int,
    ollama_url: str | None = None,
) -> GunaRouter:
    """
    Create a fully initialized GunaRouter.

    Usage:
        router = await create_guna_router(tenant_id=1)
        result = await router.route("Process invoice")
    """
    # Create embedder
    embedder = OllamaEmbedder(base_url=ollama_url)

    # Create semantic router
    semantic = SanskritiSemanticRouter(
        tenant_id=tenant_id,
        embedder=embedder,
    )
    await semantic.initialize()

    # Create deterministic router
    deterministic = DeterministicRouter()

    # Create GunaRouter
    return GunaRouter(
        tenant_id=tenant_id,
        deterministic_router=deterministic,
        semantic_router=semantic,
    )
