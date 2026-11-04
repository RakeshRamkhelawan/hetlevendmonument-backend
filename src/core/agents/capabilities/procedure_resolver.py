"""
Slice 9: ProcedureResolver - Orchestration of All Capability Agents

Coordinates DomainPackRegistry, ConfidenceScorer, PlannerAgent, ComplianceAgent,
ReviewerAgent, and ExecutorAgent for complete procedure resolution.
"""

from typing import Any, Optional
from uuid import UUID, uuid4

from src.core.agents.capabilities.schemas import (
    ComplianceResult,
    ComplianceStatus,
    ExecutionDecision,
    ExecutionStep,
    PlannerResult,
    ProcedureResolverInput,
    ProcedureResolverOutput,
    ScoredProcedure,
)


class ProcedureResolver:
    """
    Orchestrates all capability agents to resolve user intent to executable procedures

    Resolution Flow:
    1. Get candidate procedures (DomainPackRegistry)
    2. Score candidates (ConfidenceScorer)
    3. Determine decision based on confidence
    4. Create execution plan (PlannerAgent) if needed
    5. Check compliance (ComplianceAgent)
    6. Request review (ReviewerAgent) if needed
    7. Return resolution result
    """

    def __init__(self) -> None:
        """Initialize procedure resolver with mock services"""
        # In production, these would be injected dependencies
        self._mock_procedures = self._initialize_mock_procedures()

    def _initialize_mock_procedures(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Initialize mock procedure database for testing"""
        return [
            {
                "procedure_id": uuid4(),
                "procedure_name": "Invoice Approval Procedure",
                "domain_pack_id": uuid4(),
                "tags": ["invoice", "approve", "finance", "payment"],
                "domain": "finance",
            },
            {
                "procedure_id": uuid4(),
                "procedure_name": "User Profile Update",
                "domain_pack_id": uuid4(),
                "tags": ["profile", "user", "update", "view"],
                "domain": "user",
            },
            {
                "procedure_id": uuid4(),
                "procedure_name": "Data Export Procedure",
                "domain_pack_id": uuid4(),
                "tags": ["export", "data", "download"],
                "domain": "data",
            },
        ]

    async def resolve(
        self,
        input_data: ProcedureResolverInput,
    ) -> ProcedureResolverOutput:
        """
        Resolve user intent to executable procedure

        Args:
            input_data: User intent and context

        Returns:
            ProcedureResolverOutput with decision and execution plan
        """
        try:
            # Step 1: Get candidate procedures
            candidates = await self._get_candidates(
                input_data.user_intent,
                input_data.tenant_id,
                input_data.domain_filter,
            )

            if not candidates:
                return self._no_match_result("No procedures found matching the intent")

            # Step 2: Score candidates
            scored = await self._score_candidates(
                input_data.user_intent,
                candidates,
                input_data.tenant_id,
                input_data.user_id,
            )

            if not scored:
                return self._no_match_result("No procedures could be scored")

            # Step 3: Get top match and determine decision
            top_match = scored[0]
            ambiguous = self._detect_ambiguous_matches(scored)

            # Step 4: Determine execution decision
            decision, confidence = self._determine_decision(
                top_match,
                ambiguous,
            )

            # Step 5: Create execution plan if needed
            execution_plan = None
            if decision in [
                ExecutionDecision.AUTO_EXECUTE,
                ExecutionDecision.USER_CONFIRM,
            ]:
                execution_plan = await self._create_plan(
                    input_data.user_intent,
                    top_match,
                    input_data.tenant_id,
                    input_data.user_id,
                )

                # Step 6: Check compliance
                compliance = await self._check_compliance(
                    execution_plan,
                    input_data.tenant_id,
                    input_data.user_id,
                )

                # Override decision if compliance blocked
                if compliance.status == ComplianceStatus.BLOCKED:
                    decision = ExecutionDecision.NO_MATCH
                    return ProcedureResolverOutput(
                        decision=decision,
                        matched_procedure=top_match,
                        execution_plan=None,
                        confidence=confidence,
                        reasoning="Procedure blocked by compliance policy",
                        ambiguous_alternatives=ambiguous,
                    )

            # Step 7: Build reasoning
            reasoning = self._build_reasoning(
                decision,
                top_match,
                ambiguous,
                confidence,
            )

            return ProcedureResolverOutput(
                decision=decision,
                matched_procedure=top_match,
                execution_plan=execution_plan,
                confidence=confidence,
                reasoning=reasoning,
                ambiguous_alternatives=ambiguous,
            )

        except Exception as e:
            # Graceful degradation on errors
            return self._no_match_result("Error during resolution: Service unavailable")

    async def _get_candidates(
        self,
        user_intent: str,
        tenant_id: UUID,
        domain_filter: str | None,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get candidate procedures from registry"""
        # Mock implementation - in production, query DomainPackRegistry
        candidates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Extract keywords from intent
        keywords = user_intent.lower().split()

        for proc in self._mock_procedures:
            # Filter by domain if specified
            if domain_filter and proc["domain"] != domain_filter:
                continue

            # Check if any keyword matches procedure tags
            matches = any(keyword in tag for keyword in keywords for tag in proc["tags"])

            if matches:
                candidates.append(proc)

        return candidates

    async def _score_candidates(
        self,
        user_intent: str,
        candidates: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        tenant_id: UUID,
        user_id: UUID,
    ) -> list[ScoredProcedure]:
        """Score candidate procedures using ConfidenceScorer"""
        # Mock implementation - in production, use ConfidenceScorer
        scored: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for proc in candidates:
            # Simple tag-based scoring
            keywords = set(user_intent.lower().split())
            tags = set(proc["tags"])
            matching_tags = keywords.intersection(tags)

            # Calculate tag score (ratio of matching keywords)
            tag_score = len(matching_tags) / max(len(keywords), 1) if keywords else 0.0

            # If we have multiple matching tags, boost score significantly
            if len(matching_tags) >= 2:
                # Strong match - at least 2 keywords match tags
                confidence = min(0.85 + (len(matching_tags) * 0.05), 0.95)
            elif len(matching_tags) == 1:
                # Medium match - 1 keyword matches
                confidence = 0.65
            else:
                # Weak match - no direct tag matches
                confidence = 0.3

            # Create scored procedure
            scored_proc = ScoredProcedure(
                procedure_id=proc["procedure_id"],
                procedure_name=proc["procedure_name"],
                domain_pack_id=proc["domain_pack_id"],
                confidence_score=confidence,
                tag_score=tag_score,
                semantic_score=0.5,  # Neutral
                history_score=0.5,  # Neutral
                recency_score=0.5,  # Neutral
                user_override_score=0.0,
                is_ambiguous=False,
            )
            scored.append(scored_proc)

        # Sort by confidence descending
        scored.sort(key=lambda x: x.confidence_score, reverse=True)

        return scored

    def _detect_ambiguous_matches(
        self,
        scored: list[ScoredProcedure],
    ) -> list[ScoredProcedure]:
        """Detect ambiguous matches (top 2+ within 0.1 confidence)"""
        if len(scored) < 2:
            return []

        top_score = scored[0].confidence_score
        ambiguous: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for proc in scored[1:]:
            if abs(top_score - proc.confidence_score) < 0.1:
                ambiguous.append(proc)

        return ambiguous

    def _determine_decision(
        self,
        top_match: ScoredProcedure,
        ambiguous: list[ScoredProcedure],
    ) -> tuple[ExecutionDecision, float]:
        """Determine execution decision based on confidence"""
        confidence = top_match.confidence_score

        # Ambiguous matches require confirmation
        if ambiguous:
            return ExecutionDecision.USER_CONFIRM, confidence

        # High confidence -> auto-execute
        if confidence >= 0.8:
            return ExecutionDecision.AUTO_EXECUTE, confidence

        # Medium confidence -> user confirmation
        if confidence >= 0.5:
            return ExecutionDecision.USER_CONFIRM, confidence

        # Low confidence -> no match
        return ExecutionDecision.NO_MATCH, confidence

    async def _create_plan(
        self,
        user_intent: str,
        procedure: ScoredProcedure,
        tenant_id: UUID,
        user_id: UUID,
    ) -> PlannerResult:
        """Create execution plan using PlannerAgent"""
        # Mock implementation - in production, use PlannerAgent
        steps = [
            ExecutionStep(
                step_number=1,
                action="validate_request",
                description=f"Validate user request: {user_intent}",
                parameters={},
                compliance_checks=["rbac", "tenant"],
            ),
            ExecutionStep(
                step_number=2,
                action="execute_procedure",
                description=f"Execute {procedure.procedure_name}",
                parameters={"procedure_id": str(procedure.procedure_id)},
                compliance_checks=["data_privacy"],
            ),
        ]

        return PlannerResult(
            execution_plan=steps,
            estimated_duration_minutes=5,
            confidence_in_plan=0.9,
            decision=ExecutionDecision.AUTO_EXECUTE,
            reasoning=f"Matched procedure: {procedure.procedure_name}",
            requires_human_approval=False,
        )

    async def _check_compliance(
        self,
        plan: PlannerResult,
        tenant_id: UUID,
        user_id: UUID,
    ) -> ComplianceResult:
        """Check compliance using ComplianceAgent"""
        # Mock implementation - in production, use ComplianceAgent
        # For now, always allow
        return ComplianceResult(
            status=ComplianceStatus.ALLOWED,
            issues=[],
            passed_checks=["rbac", "tenant", "data_privacy"],
        )

    def _build_reasoning(
        self,
        decision: ExecutionDecision,
        top_match: ScoredProcedure,
        ambiguous: list[ScoredProcedure],
        confidence: float,
    ) -> str:
        """Build human-readable reasoning for decision"""
        if decision == ExecutionDecision.AUTO_EXECUTE:
            return (
                f"High confidence match ({confidence:.2f}): "
                f"{top_match.procedure_name}. Executing automatically."
            )

        if decision == ExecutionDecision.USER_CONFIRM:
            if ambiguous:
                return (
                    f"Ambiguous match ({confidence:.2f}): "
                    f"{top_match.procedure_name} and {len(ambiguous)} other(s). "
                    f"User confirmation required."
                )
            return (
                f"Medium confidence match ({confidence:.2f}): "
                f"{top_match.procedure_name}. User confirmation required."
            )

        # NO_MATCH
        return f"Low confidence ({confidence:.2f}). No clear procedure match found."

    def _no_match_result(self, reason: str) -> ProcedureResolverOutput:
        """Return a no-match result with reason"""
        return ProcedureResolverOutput(
            decision=ExecutionDecision.NO_MATCH,
            matched_procedure=None,
            execution_plan=None,
            confidence=0.0,
            reasoning=reason,
            ambiguous_alternatives=[],
        )
