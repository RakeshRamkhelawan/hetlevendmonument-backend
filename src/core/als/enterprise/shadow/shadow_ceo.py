"""
ShadowCEO - Red Teaming and Adversarial Security

The ShadowCEO operates in parallel to the ChiefOrchestrator,
constantly probing for vulnerabilities, attack vectors, and
potential failures. It can veto decisions that exceed risk
tolerance.

Inspired by:
- Red teaming methodologies
- Byzantine fault tolerance
- Adversarial ML robustness testing
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier
from src.core.shared.interfaces import TaskData

logger = logging.getLogger("ShadowCEO")


class RiskLevel(Enum):
    """Risk severity levels."""

    NONE = 0  # No risk detected
    LOW = 1  # Acceptable risk
    MEDIUM = 2  # Monitor closely
    HIGH = 3  # Require additional approval
    CRITICAL = 4  # Auto-veto


@dataclass
class VetoDecision:
    """A veto decision from the ShadowCEO."""

    decision_id: str
    original_task_id: str
    veto_reason: str
    risk_level: RiskLevel
    risk_factors: list[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    shadow_agent_id: str = "shadow_ceo"
    override_possible: bool = False  # Can Chief override?
    override_requirements: list[str] = field(default_factory=list)


@dataclass
class ThreatPattern:
    """Detected threat pattern for learning."""

    pattern_id: str
    pattern_type: str  # "byzantine", "adversarial", "failure_cascade"
    signature: str  # Hash of pattern characteristics
    frequency: int = 1
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    departments_affected: set[Department] = field(default_factory=set)


class ShadowCEO:
    """
    ShadowCEO - Adversarial Security Monitor.

    The ShadowCEO runs continuously in the background, analyzing:
    - Task delegation patterns for failure risks
    - Cross-department contracts for attack vectors
    - Agent behavior for Byzantine faults
    - System-wide risk accumulation

    It maintains:
    - threat_vetoes: List[Any] of decisions it has blocked  # TODO(TYPE): replace Any with concrete type
    - risk_level: Current system-wide risk assessment

    SP-AGT-008: Check 6 uses CritiqueStore avg score as risk signal (threshold 0.35).
    Threshold is intentionally lower than HITL threshold (0.40) for early ShadowCEO warning.
    """

    # SP-AGT-008: critique score below this triggers HIGH risk in review_task() Check 6.
    # Intentionally < CritiqueStore._HITL_SCORE_THRESHOLD (0.40): early warning before HITL.
    _CRITIQUE_RISK_THRESHOLD: float = 0.35

    def __init__(
        self, tenant_id: int, signal_bus: SignalBus | None = None, agent_id: str = "shadow_ceo"
    ) -> None:
        self.tenant_id = tenant_id
        self.signal_bus = signal_bus
        self.agent_id = agent_id

        # State
        self.threat_vetoes: list[VetoDecision] = []
        self.current_risk_level = RiskLevel.NONE
        self.threat_memory: dict[str, ThreatPattern] = {}

        # Risk thresholds
        self.risk_thresholds = {
            "task_complexity": 0.8,  # Veto if complexity > 0.8
            "cross_dept_risk": 0.7,  # Veto if cross-dept risk > 0.7
            "byzantine_probability": 0.6,  # Veto if Byzantine fault prob > 0.6
            "cascade_risk": 0.5,  # Veto if failure cascade risk > 0.5
        }

        # Monitoring
        self._monitor_task: (
            asyncio.Task[Any] | None  # TODO(TYPE): replace Any with concrete type
        ) = None
        self._running = False

        # Metrics
        self.veto_count = 0
        self.override_count = 0

        logger.info(
            "ShadowCEO initialized",
            extra={"tenant_id": tenant_id, "agent_id": agent_id},
        )

    async def initialize(self) -> bool:
        """Initialize ShadowCEO monitoring."""
        try:
            self._running = True
            # Continuous monitoring task
            self._monitor_task = asyncio.create_task(self._continuous_monitoring())

            logger.info(f"ShadowCEO monitoring active for tenant {self.tenant_id}")
            return True

        except Exception as e:
            logger.error(f"ShadowCEO initialization failed: {e}")
            return False

    async def review_task(
        self,
        task: TaskData,
        proposed_agent: str,
        proposed_department: Department | None = None,
        active_contracts: list[str] | None = None,
    ) -> VetoDecision | None:
        """
        Review a task before delegation.

        Returns VetoDecision if task should be blocked,
        or None if task is approved.
        """
        risk_factors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        max_risk = RiskLevel.NONE

        # Check 1: Task complexity risk
        complexity = self._assess_complexity(task)
        if complexity > self.risk_thresholds["task_complexity"]:
            risk_factors.append(f"High complexity: {complexity:.2f}")
            max_risk = RiskLevel(max(max_risk.value, RiskLevel.HIGH.value))

        # Check 2: Cross-department risk
        if active_contracts:
            cross_risk = self._assess_cross_dept_risk(active_contracts)
            if cross_risk > self.risk_thresholds["cross_dept_risk"]:
                risk_factors.append(f"Cross-dept risk: {cross_risk:.2f}")
                max_risk = RiskLevel(max(max_risk.value, RiskLevel.MEDIUM.value))

        # Check 3: Byzantine fault probability
        byzantine_prob = self._assess_byzantine_risk(proposed_agent, task)
        if byzantine_prob > self.risk_thresholds["byzantine_probability"]:
            risk_factors.append(f"Byzantine fault risk: {byzantine_prob:.2f}")
            max_risk = RiskLevel(max(max_risk.value, RiskLevel.HIGH.value))

        # Check 4: Failure cascade risk
        cascade_risk = self._assess_cascade_risk(task, proposed_department)
        if cascade_risk > self.risk_thresholds["cascade_risk"]:
            risk_factors.append(f"Cascade risk: {cascade_risk:.2f}")
            max_risk = RiskLevel(max(max_risk.value, RiskLevel.CRITICAL.value))

        # Check 5: Known threat patterns
        threat_match = self._check_threat_patterns(task, proposed_agent)
        if threat_match:
            risk_factors.append(f"Matches threat pattern: {threat_match}")
            max_risk = RiskLevel(max(max_risk.value, RiskLevel.CRITICAL.value))

        # Check 6: Critique score signal (SP-AGT-008)
        critique_risk, critique_reason = await self._assess_critique_risk(proposed_agent)
        if critique_risk != RiskLevel.NONE and critique_reason:
            risk_factors.append(critique_reason)
            max_risk = RiskLevel(max(max_risk.value, critique_risk.value))

        # Update system risk level
        self.current_risk_level = max_risk

        # Create veto if risk exceeds threshold
        if max_risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            import uuid

            veto = VetoDecision(
                decision_id=f"veto_{uuid.uuid4().hex[:12]}",
                original_task_id=task.id,
                veto_reason=f"Risk level {max_risk.name}: {', '.join(risk_factors)}",
                risk_level=max_risk,
                risk_factors=risk_factors,
                shadow_agent_id=self.agent_id,
                override_possible=(max_risk == RiskLevel.HIGH),
                override_requirements=(
                    ["manual_approval", "risk_acknowledgment", "fallback_plan"]
                    if max_risk == RiskLevel.HIGH
                    else []
                ),
            )

            self.threat_vetoes.append(veto)
            self.veto_count += 1

            # Emit veto signal
            await self._emit_veto_signal(veto)

            logger.warning(
                "Task vetoed by ShadowCEO",
                extra={
                    "task_id": task.id,
                    "risk_level": max_risk.name,
                    "veto_id": veto.decision_id,
                },
            )

            return veto

        return None  # Task approved

    async def _assess_critique_risk(self, proposed_agent: str) -> tuple[RiskLevel, str | None]:
        """Pull recent critique scores for proposed_agent from CritiqueStore.

        Returns (RiskLevel.NONE, None) when no data exists or on any error.
        Lazy import keeps agents -> critique_store as Cat B in .importlinter.
        """
        try:
            from src.core.agents.critique_store import get_critique_store  # noqa: PLC0415

            store = get_critique_store()
            critiques = await store.get_by_agent(
                tenant_id=self.tenant_id,
                agent_name=proposed_agent,
                limit=10,
            )
            if not critiques:
                return RiskLevel.NONE, None
            avg_score = sum(c.score for c in critiques) / len(critiques)
            if avg_score < self._CRITIQUE_RISK_THRESHOLD:
                return RiskLevel.HIGH, f"critique_score_low avg={avg_score:.2f}"
            return RiskLevel.NONE, None
        except Exception as e:
            logger.error(
                "shadow_ceo critique risk check failed: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
            )
            return RiskLevel.NONE, None

    async def review_contract(
        self, contract_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[bool, list[str]]:
        """
        Review an A2A contract for security risks.

        Returns (is_safe, list_of_concerns)
        """
        concerns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for suspicious data schemas
        schema = contract_data.get("required_schema", {})
        if self._is_schema_suspicious(schema):
            concerns.append("Suspicious data schema (potential data exfiltration)")

        # Check for extreme deadlines
        deadline = contract_data.get("deadline_ms", 5000)
        if deadline < 100:  # Less than 100ms
            concerns.append("Extremely short deadline (potential DoS)")

        # Check for asymmetric prana costs
        prana_cost = contract_data.get("prana_cost", 50)
        if prana_cost > 1000:
            concerns.append("Extremely high prana cost (resource exhaustion)")

        # Check cross-department risk
        producer_dept = contract_data.get("producer_department")
        consumer_dept = contract_data.get("consumer_department")
        if producer_dept and consumer_dept:
            if self._is_high_rust_dept_pair(producer_dept, consumer_dept):
                concerns.append(f"High-risk dept pair: {producer_dept}-{consumer_dept}")

        is_safe = len(concerns) == 0

        if not is_safe:
            logger.warning(
                "Contract security concerns",
                extra={
                    "contract_id": contract_data.get("contract_id"),
                    "concerns": concerns,
                },
            )

        return is_safe, concerns

    def get_risk_report(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current risk assessment report."""
        return {
            "tenant_id": self.tenant_id,
            "current_risk_level": self.current_risk_level.name,
            "total_vetoes_issued": self.veto_count,
            "total_overrides": self.override_count,
            "active_vetoes": len(
                [v for v in self.threat_vetoes if v.risk_level == RiskLevel.CRITICAL]
            ),
            "threat_patterns_learned": len(self.threat_memory),
            "recent_vetoes": [
                {
                    "veto_id": v.decision_id,
                    "task_id": v.original_task_id,
                    "risk_level": v.risk_level.name,
                    "reason": v.veto_reason,
                    "timestamp": v.timestamp.isoformat(),
                }
                for v in self.threat_vetoes[-10:]  # Last 10
            ],
        }

    async def report_byzantine_agent(
        self, agent_id: str, evidence: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Report a potentially malicious/faulty agent."""
        # Create threat pattern
        pattern_id = f"byzantine_{agent_id}_{datetime.now(timezone.utc).timestamp()}"
        signature = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()[:16]

        threat = ThreatPattern(
            pattern_id=pattern_id,
            pattern_type="byzantine",
            signature=signature,
            frequency=1,
            departments_affected=(
                {Department(evidence.get("department"))} if evidence.get("department") else set()
            ),
        )

        self.threat_memory[pattern_id] = threat

        # Emit alert
        if self.signal_bus:
            await self.signal_bus.emit(
                Signal(
                    tenant_id=self.tenant_id,
                    source_agent_id=self.agent_id,
                    target_agent_ids=["chief_orchestrator"],
                    tier=SignalTier.REFLEX,
                    payload={
                        "alert_type": "byzantine_agent",
                        "agent_id": agent_id,
                        "evidence": evidence,
                        "pattern_id": pattern_id,
                    },
                )
            )

        logger.critical(
            "Byzantine agent reported",
            extra={"agent_id": agent_id, "pattern_id": pattern_id},
        )

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info(f"ShadowCEO shutdown for tenant {self.tenant_id}")

    # Internal methods

    def _assess_complexity(self, task: TaskData) -> float:
        """Assess task complexity (0.0 - 1.0)."""
        score = 0.0

        # Based on task metadata
        metadata = task.metadata or {}

        # Complexity factors
        if metadata.get("subtasks", 0) > 5:
            score += 0.3
        if metadata.get("dependencies", 0) > 3:
            score += 0.2
        if metadata.get("requires_human_review", False):
            score += 0.2
        if len(task.tags) > 5:
            score += 0.1

        # Based on task title
        complex_types = [
            "ma_analysis",
            "audit",
            "compliance_review",
            "security_incident",
        ]
        if any(ct in task.title.lower() for ct in complex_types):
            score += 0.3

        return min(score, 1.0)

    def _assess_cross_dept_risk(self, contracts: list[str]) -> float:
        """Assess risk from cross-department contracts."""
        # More contracts = higher coordination risk
        base_risk = len(contracts) * 0.1
        return min(base_risk, 1.0)

    def _assess_byzantine_risk(self, agent_id: str, task: TaskData) -> float:
        """Assess probability of Byzantine fault."""
        # Check agent history in threat memory
        agent_threats = [t for t in self.threat_memory.values() if t.pattern_type == "byzantine"]

        if not agent_threats:
            return 0.0

        # Higher frequency = higher risk
        max_freq = max(t.frequency for t in agent_threats)
        return min(max_freq * 0.1, 1.0)

    def _assess_cascade_risk(self, task: TaskData, department: Department | None) -> float:
        """Assess risk of failure cascade."""
        score = 0.0

        # Critical departments have higher cascade potential
        if department in [Department.IT_SECURITY, Department.FINANCE]:
            score += 0.3

        # Tasks with many downstream effects
        metadata = task.metadata or {}
        affected_systems = metadata.get("affected_systems", 0)
        if affected_systems > 50:
            score += 0.6
        elif affected_systems > 10:
            score += 0.4

        return min(score, 1.0)

    def _check_threat_patterns(self, task: TaskData, agent_id: str) -> str | None:
        """Check if task matches known threat patterns."""
        task_signature = hashlib.sha256(f"{task.title}:{agent_id}".encode()).hexdigest()[:16]

        for pattern in self.threat_memory.values():
            if pattern.signature == task_signature:
                pattern.frequency += 1
                pattern.last_seen = datetime.now(timezone.utc)
                return pattern.pattern_id

        return None

    def _is_schema_suspicious(
        self, schema: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Check if data schema looks suspicious."""
        # Look for excessive data requests
        if len(schema.get("schema_definition", {})) > 20:
            return True

        # Look for sensitive field names
        sensitive_keywords = ["password", "secret", "key", "token", "credential"]
        fields = str(schema).lower()
        if any(kw in fields for kw in sensitive_keywords):
            return True

        return False

    def _is_high_rust_dept_pair(self, dept1: str, dept2: str) -> bool:
        """Check if department pair is high-risk."""
        external_value = getattr(Department, "EXTERNAL", None)
        high_risk_pairs: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if external_value is not None:
            high_risk_pairs = [
                {Department.IT_SECURITY.value, external_value.value},
                {Department.FINANCE.value, external_value.value},
            ]

        pair = {dept1, dept2}
        return any(pair == hrp for hrp in high_risk_pairs if hrp)

    async def _emit_veto_signal(self, veto: VetoDecision) -> None:
        """Emit veto notification to ChiefOrchestrator."""
        signal = Signal(
            tenant_id=self.tenant_id,
            source_agent_id=self.agent_id,
            target_agent_ids=["chief_orchestrator"],
            tier=SignalTier.REFLEX,
            payload={
                "type": "veto_decision",
                "veto": {
                    "decision_id": veto.decision_id,
                    "original_task_id": veto.original_task_id,
                    "veto_reason": veto.veto_reason,
                    "risk_level": veto.risk_level.name,
                    "risk_factors": veto.risk_factors,
                    "override_possible": veto.override_possible,
                },
            },
        )

        if self.signal_bus:
            await self.signal_bus.emit(signal)

    async def _continuous_monitoring(self) -> None:
        """Continuously monitor system for threats."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute

                # Decay risk level over time
                if self.current_risk_level.value > 0:
                    # Risk decays slowly
                    pass  # Risk stays until explicitly cleared

                # Clean up old veto decisions
                cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
                self.threat_vetoes = [v for v in self.threat_vetoes if v.timestamp > cutoff]

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ShadowCEO monitoring error: {e}")

    async def _listen_for_signals(self) -> None:
        """Listen for signals to analyze."""
        raise NotImplementedError(
            "ShadowCEO background listener is not yet wired to Redis streams. See ADR-006."
        )


# Import timedelta at end to avoid circular import issues
from datetime import timedelta
