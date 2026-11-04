"""
Gatekeeper - Deterministic Policy Enforcement Layer

The Gatekeeper serves as the final "compile step" before any action is executed.
It is completely deterministic (NO LLM) and enforces hard security policies.

Key Responsibilities:
1. Enforce HIGH_RISK policies (Legal/Finance/PII require ShadowCEO OK or HITL)
2. Process ShadowCEO vetoes and determine if override is possible
3. Inject Human-in-the-Loop (HITL) for sensitive operations
4. Maintain audit trail of all gate decisions

Inspired by:
- Security policy enforcement engines
- Deterministic access control
- Compliance frameworks (SOC2, GDPR)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

import yaml

if TYPE_CHECKING:
    from src.core.als.enterprise.gatekeeper_repository import GatekeeperRepository

from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.als.enterprise.shadow.shadow_ceo import RiskLevel, VetoDecision
from src.core.shared.interfaces import TaskData

logger = logging.getLogger("Gatekeeper")


class GateDecision(Enum):
    """Possible gatekeeper decisions."""

    ALLOW = "allow"  # Action approved, proceed
    BLOCK = "block"  # Action blocked, do not proceed
    REQUIRE_HITL = "hitl"  # Human-in-the-loop required
    DEFER = "defer"  # Defer decision (e.g., wait for more info)


class RiskCategory(Enum):
    """Risk categories for policy evaluation."""

    LOW = "low"  # Standard operations
    MEDIUM = "medium"  # Sensitive but routine
    HIGH = "high"  # Legal/Finance/PII - requires additional checks
    CRITICAL = "critical"  # System-level changes - requires override + HITL


@dataclass
class PolicyRule:
    """A single policy rule."""

    rule_id: str
    name: str
    description: str
    risk_categories: set[RiskCategory]
    required_approvals: list[str]  # e.g., ["shadow_ceo", "manual_approval"]
    conditions: dict[
        str, Any  # TODO(TYPE): replace Any with concrete type
    ]  # e.g., {"max_amount": 10000}  # TODO(TYPE): replace Any with concrete type
    enabled: bool = True


@dataclass
class GateDecisionRecord:
    """Record of a gatekeeper decision."""

    decision_id: str
    timestamp: datetime
    task_id: str
    tenant_id: int
    decision: GateDecision
    risk_category: RiskCategory
    risk_level: RiskLevel
    shadow_ceo_veto: VetoDecision | None
    policy_rules_checked: list[str]
    policy_rules_failed: list[str]
    hitl_required: bool
    hitl_ticket_ref: str | None
    override_used: bool
    decision_hash: str  # SHA-256 for tamper evidence
    previous_hash: str | None = None  # Chain link (None for genesis)

    def compute_hash(self) -> str:
        """Compute tamper-evident hash of decision (legacy, use compute_chain_hash)."""
        return self.compute_chain_hash()

    def compute_chain_hash(self, previous_hash: str | None = None) -> str:
        """Compute tamper-evident hash chained to previous decision (per tenant).

        IMPORTANT: The chain is PER TENANT. Tenant A's chain is completely separate
        from Tenant B's chain. This is required for tenant isolation and compliance.

        Args:
            previous_hash: Hash of the previous decision in this tenant's chain.
                          Use "genesis" for the first decision of a tenant.

        Returns:
            Full SHA-256 hash (64 chars) of this decision including chain link.
        """
        data = {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,  # CRITICAL: tenant in hash for isolation
            "decision": self.decision.value,
            "risk_category": self.risk_category.value,
            "risk_level": self.risk_level.value,
            "override_used": self.override_used,
            "previous_hash": previous_hash or "genesis",
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()  # Full 64 chars


@dataclass
class HITLRequest:
    """Human-in-the-Loop request."""

    request_id: str
    task_id: str
    tenant_id: int
    reason: str
    risk_factors: list[str]
    requested_at: datetime
    ticket_ref: str
    status: str = "pending"  # pending, approved, rejected, expired
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    agent_id: str | None = None  # SP-GOV-ARCH-7: agent this ticket concerns
    # ADR-036 OP-81: het gebruikersnummer van de MENS namens wie de agent dit aanvroeg.
    # `agent_id` zegt WIE handelde, dit zegt VOOR WIE. Alleen op de tweede kan de
    # zelf-goedkeuringscheck rusten (OWASP ASVS 5.0 8.3.3).
    requested_by_user_id: int | None = None


def _als_gebruikersnummer(waarde: object) -> int | None:
    """De aanvragende mens als gebruikersnummer, of `None` (ADR-036 OP-81).

    `context` is een losse `dict[str, Any]`, dus de waarde kan alles zijn. Fout raden is hier niet
    gratis: een verkeerd getal zou een WILLEKEURIGE gebruiker als aanvrager vastleggen en daarmee
    een onterechte 403 op de goedkeurroute geven. Alleen een echt geheel getal of een zuiver
    decimale ASCII-string telt.

    `isascii() and isdecimal()` en NIET `isdigit()`: dat laatste is True voor Arabisch-Indische
    cijfers en voor superscripts, waarop `int()` een ValueError gooit. Dezelfde valkuil is op het
    broker-pad al een keer betaald (ADR-036 OP-106).

    `bool` wordt expliciet geweigerd: `isinstance(True, int)` is True in Python, en gebruiker 1
    zijn omdat er ergens een vlag in de context stond is precies de stille verwisseling die deze
    controle moet voorkomen.
    """
    if isinstance(waarde, bool):
        return None
    if isinstance(waarde, int):
        return waarde
    tekst = str(waarde or "").strip()
    if not (tekst.isascii() and tekst.isdecimal()):
        return None
    try:
        return int(tekst)
    except ValueError:
        # CPython weigert vanaf 3.11 int()-conversie boven 4300 cijfers (een DoS-afscherming
        # in de taal zelf, PEP 655-gerelateerd) en gooit dan een ValueError ondanks dat
        # isdecimal() al True was. Gemeten 2026-09-09 (security-review OP-81): een 5000-cijferige
        # string crasht deze functie. Vandaag heeft `context` geen enkele levende aanroeper
        # (zie OP-221), dus onbereikbaar in productie -- maar fail-closed naar None is hier
        # de juiste default zodra dat verandert, net als bij elke andere onherkenbare waarde.
        return None


class Gatekeeper:
    """
    Gatekeeper - Deterministic Policy Enforcement

    The Gatekeeper is the final checkpoint before any action is executed.
    It operates with zero ambiguity - same input always produces same output.

    Usage:
        gatekeeper = Gatekeeper(tenant_id=123)

        # Evaluate a task
        decision = await gatekeeper.evaluate_task(
            task=task_data,
            proposed_department=Department.FINANCE,
            shadow_ceo_veto=None
        )

        if decision.decision == GateDecision.ALLOW:
            # Proceed with execution
            pass
        elif decision.decision == GateDecision.REQUIRE_HITL:
            # Wait for human approval
            pass
        else:
            # BLOCK - do not proceed
            pass
    """

    # High-risk task types requiring additional scrutiny
    HIGH_RISK_TASK_TYPES: set[str] = {
        "process_payment",
        "transfer_funds",
        "modify_employee_contract",
        "access_pii",
        "delete_records",
        "modify_access_controls",
        "deploy_to_production",
        "process_credit_card",
    }

    # Sensitive departments
    SENSITIVE_DEPARTMENTS: set[Department] = {
        Department.FINANCE,
        Department.IT_SECURITY,
    }

    def __init__(
        self,
        tenant_id: int,
        config_path: str | None = None,
        repository: Optional["GatekeeperRepository"] = None,
        db_session: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.tenant_id = tenant_id
        self._decision_log: list[GateDecisionRecord] = []
        self._hitl_requests: dict[str, HITLRequest] = {}
        self._policy_rules: dict[str, PolicyRule] = {}
        self._repository = repository
        self._db_session = db_session

        # Initialize policies from YAML or use defaults
        if config_path:
            self._load_policies_from_yaml(config_path)
        else:
            self._init_default_policies()

        logger.info(f"Gatekeeper initialized for tenant {tenant_id}")

    def _init_default_policies(self) -> None:
        """Initialize default policy rules."""

        # Policy 1: PII Access Requires HITL
        self._policy_rules["PII_ACCESS"] = PolicyRule(
            rule_id="POL-001",
            name="PII Access Control",
            description="Access to personally identifiable information requires approval",
            risk_categories={RiskCategory.HIGH, RiskCategory.CRITICAL},
            required_approvals=["manual_approval"],
            conditions={"requires_justification": True},
        )

        # Policy 2: Financial Operations Require ShadowCEO + HITL
        self._policy_rules["FINANCIAL_OPS"] = PolicyRule(
            rule_id="POL-002",
            name="Financial Operations",
            description="Financial transactions over threshold require dual approval",
            risk_categories={RiskCategory.HIGH},
            required_approvals=["shadow_ceo", "manual_approval"],
            conditions={"amount_threshold": 10000},
        )

        # Policy 3: ShadowCEO Veto Cannot Be Overridden for Critical
        self._policy_rules["VETO_CRITICAL"] = PolicyRule(
            rule_id="POL-003",
            name="Critical Veto Enforcement",
            description="ShadowCEO CRITICAL vetoes cannot be overridden",
            risk_categories={RiskCategory.CRITICAL},
            required_approvals=[],  # No override possible
            conditions={},
        )

        # Policy 4: Cross-Department Contracts Require Monitoring
        self._policy_rules["CROSS_DEPT"] = PolicyRule(
            rule_id="POL-004",
            name="Cross-Department Monitoring",
            description="Contracts spanning departments require additional monitoring",
            risk_categories={RiskCategory.MEDIUM, RiskCategory.HIGH},
            required_approvals=["shadow_ceo"],
            conditions={},
        )

    def _load_policies_from_yaml(self, config_path: str) -> None:
        """Load policy rules from YAML configuration file.

        Falls back to default policies if YAML file is not found.
        Validates that required fields are present and risk categories are valid.

        Args:
            config_path: Path to the YAML configuration file

        Raises:
            yaml.YAMLError: If YAML syntax is invalid
            ValueError: If required fields are missing or risk categories are invalid
        """
        from pathlib import Path

        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Policy config not found at {config_path}, using hardcoded defaults")
            self._init_default_policies()
            return

        try:
            with open(path, encoding="utf-8") as f:
                policies_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML at {config_path}: {e}")
            raise

        if not policies_data or "policies" not in policies_data:
            logger.warning(f"No policies found in {config_path}, using defaults")
            self._init_default_policies()
            return

        required_fields = {
            "rule_id",
            "name",
            "description",
            "risk_categories",
            "required_approvals",
        }

        for policy_data in policies_data.get("policies", []):
            # Validate required fields
            missing_fields = required_fields - set(policy_data.keys())
            if missing_fields:
                raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

            # Skip disabled policies
            if not policy_data.get("enabled", True):
                continue

            # Convert risk categories from strings to RiskCategory enum
            try:
                risk_cats = {RiskCategory(cat.lower()) for cat in policy_data["risk_categories"]}
            except ValueError as e:
                valid_values = [rc.value for rc in RiskCategory]
                raise ValueError(
                    f"Invalid RiskCategory in policy {policy_data.get('rule_id', 'unknown')}: {e}. "
                    f"Valid values are: {', '.join(valid_values)}"
                ) from e

            # Create PolicyRule instance
            rule = PolicyRule(
                rule_id=policy_data["rule_id"],
                name=policy_data["name"],
                description=policy_data["description"],
                risk_categories=risk_cats,
                required_approvals=policy_data["required_approvals"],
                conditions=policy_data.get("conditions", {}),
                enabled=policy_data.get("enabled", True),
            )
            self._policy_rules[policy_data["rule_id"]] = rule

        logger.info(f"Loaded {len(self._policy_rules)} policies from {config_path}")

    def _get_last_decision_hash(self) -> str | None:
        """Get hash of most recent decision for THIS TENANT's chain linking.

        Returns:
            The decision_hash of the most recent decision for this tenant,
            or None if this tenant has no decisions yet (genesis).
        """
        tenant_decisions = [d for d in self._decision_log if d.tenant_id == self.tenant_id]
        if tenant_decisions:
            return tenant_decisions[-1].decision_hash
        return None

    async def evaluate_task(
        self,
        task: TaskData,
        proposed_department: Department,
        shadow_ceo_veto: VetoDecision | None = None,
        active_contracts: list[str] | None = None,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> GateDecisionRecord:
        """
        Evaluate a task and return a gate decision.

        This is the main entry point for policy enforcement.
        Completely deterministic - same inputs always produce same outputs.
        """
        import uuid

        decision_id = f"gate_{uuid.uuid4().hex[:16]}"
        policy_rules_checked: list[str] = []
        policy_rules_failed: list[str] = []

        # Step 1: Determine risk category
        risk_category = self._categorize_risk(task, proposed_department)

        # Step 2: Check ShadowCEO veto
        if shadow_ceo_veto:
            veto_decision = self._process_shadow_ceo_veto(shadow_ceo_veto)
            if veto_decision == GateDecision.BLOCK:
                # Critical veto - cannot proceed
                record = GateDecisionRecord(
                    decision_id=decision_id,
                    timestamp=datetime.now(timezone.utc),
                    task_id=task.id,
                    tenant_id=self.tenant_id,
                    decision=GateDecision.BLOCK,
                    risk_category=risk_category,
                    risk_level=shadow_ceo_veto.risk_level,
                    shadow_ceo_veto=shadow_ceo_veto,
                    policy_rules_checked=["VETO_CRITICAL"],
                    policy_rules_failed=["VETO_CRITICAL"],
                    hitl_required=False,
                    hitl_ticket_ref=None,
                    override_used=False,
                    decision_hash="",  # Computed below
                )
                # Compute chain hash with previous hash
                previous_hash = self._get_last_decision_hash()
                record.previous_hash = previous_hash
                record.decision_hash = record.compute_chain_hash(previous_hash)
                self._decision_log.append(record)

                # Persist to database if repository is available (via best_effort)
                if self._repository:
                    from src.core.utils.best_effort import best_effort

                    async with best_effort("gatekeeper decision db", db_session=self._db_session):
                        await self._repository.save_decision(record)

                logger.warning(
                    f"Task {task.id} BLOCKED by ShadowCEO veto",
                    extra={"decision_id": decision_id, "veto_id": shadow_ceo_veto.decision_id},
                )
                return record
            elif veto_decision == GateDecision.REQUIRE_HITL:
                # Veto can be overridden with HITL
                policy_rules_checked.append("VETO_OVERRIDE")

        # Step 3: Evaluate policy rules
        hitl_required = False
        override_possible = False

        for rule_id, rule in self._policy_rules.items():
            if not rule.enabled:
                continue

            policy_rules_checked.append(rule_id)

            # Check if rule applies to this risk category
            if risk_category not in rule.risk_categories:
                continue

            # Check rule conditions
            if self._evaluate_rule_conditions(rule, task, context):
                if "manual_approval" in rule.required_approvals:
                    hitl_required = True
                if "shadow_ceo" in rule.required_approvals and shadow_ceo_veto:
                    if shadow_ceo_veto.override_possible:
                        override_possible = True
                    else:
                        policy_rules_failed.append(rule_id)

        # Step 4: Make final decision
        if policy_rules_failed:
            final_decision = GateDecision.BLOCK
        elif hitl_required:
            final_decision = GateDecision.REQUIRE_HITL
        else:
            final_decision = GateDecision.ALLOW

        # Step 5: Create HITL request if needed
        hitl_ticket_ref = None
        if final_decision == GateDecision.REQUIRE_HITL:
            hitl_request = self._create_hitl_request(
                task_id=task.id,
                reason=f"Risk category: {risk_category.value}",
                risk_factors=[f"Policy: {r}" for r in policy_rules_checked],
                # De MENS namens wie deze agent handelt (ADR-036 OP-81). `context` is een
                # server-side parameter van deze servicemethode -- geen request body -- en
                # `context["user_id"]` is de bestaande conventie in deze codebase voor die
                # betekenis (zie `tool_broker/hitl_router.py::_voer_goedgekeurde_actie_uit`).
                # Ontbreekt hij, dan blijft het veld leeg; dat is geen fout maar een aanvraag
                # zonder menselijke opdrachtgever.
                requested_by_user_id=_als_gebruikersnummer((context or {}).get("user_id")),
            )
            hitl_ticket_ref = hitl_request.ticket_ref
            self._hitl_requests[hitl_request.request_id] = hitl_request

        # Step 6: Create and store decision record
        record = GateDecisionRecord(
            decision_id=decision_id,
            timestamp=datetime.now(timezone.utc),
            task_id=task.id,
            tenant_id=self.tenant_id,
            decision=final_decision,
            risk_category=risk_category,
            risk_level=shadow_ceo_veto.risk_level if shadow_ceo_veto else RiskLevel.LOW,
            shadow_ceo_veto=shadow_ceo_veto,
            policy_rules_checked=policy_rules_checked,
            policy_rules_failed=policy_rules_failed,
            hitl_required=hitl_required,
            hitl_ticket_ref=hitl_ticket_ref,
            override_used=override_possible and hitl_required,
            decision_hash="",
        )
        # Compute chain hash with previous hash
        previous_hash = self._get_last_decision_hash()
        record.previous_hash = previous_hash
        record.decision_hash = record.compute_chain_hash(previous_hash)
        self._decision_log.append(record)

        # Persist to database if repository is available (via best_effort)
        if self._repository:
            from src.core.utils.best_effort import best_effort

            async with best_effort("gatekeeper decision db", db_session=self._db_session):
                await self._repository.save_decision(record)

        logger.info(
            f"Gate decision for task {task.id}: {final_decision.value}",
            extra={
                "decision_id": decision_id,
                "decision": final_decision.value,
                "risk_category": risk_category.value,
            },
        )

        return record

    def _categorize_risk(self, task: TaskData, department: Department) -> RiskCategory:
        """Determine risk category for a task."""

        # Check task title (normalize spaces to underscores for matching)
        task_title_normalized = task.title.lower().replace(" ", "_")

        # Critical: System-level changes
        critical_patterns = ["deploy", "delete_all", "modify_access"]
        if any(t in task_title_normalized for t in critical_patterns):
            return RiskCategory.CRITICAL

        # High: Financial or PII operations
        if any(t in task_title_normalized for t in self.HIGH_RISK_TASK_TYPES):
            return RiskCategory.HIGH

        # Medium: Sensitive departments
        if department in self.SENSITIVE_DEPARTMENTS:
            return RiskCategory.MEDIUM

        # Low: Everything else
        return RiskCategory.LOW

    def _process_shadow_ceo_veto(self, veto: VetoDecision) -> GateDecision:
        """Process a ShadowCEO veto and return gate decision."""

        if veto.risk_level == RiskLevel.CRITICAL:
            # CRITICAL vetoes cannot be overridden
            return GateDecision.BLOCK

        if veto.risk_level == RiskLevel.HIGH:
            # HIGH vetoes can be overridden with HITL
            if veto.override_possible:
                return GateDecision.REQUIRE_HITL
            return GateDecision.BLOCK

        # Lower risk vetoes are warnings but don't block
        return GateDecision.ALLOW

    def _evaluate_rule_conditions(
        self,
        rule: PolicyRule,
        task: TaskData,
        context: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Evaluate if a rule's conditions are met."""
        context = context or {}

        # Check amount threshold
        if "amount_threshold" in rule.conditions:
            amount = context.get("amount", 0)
            if amount < rule.conditions["amount_threshold"]:
                return False

        # Check PII access
        if "requires_justification" in rule.conditions:
            task_title = task.title.lower().replace(" ", "_")
            if "pii" in task_title or "access_pii" in task_title:
                return True

        # Default: rule applies
        return True

    def _create_hitl_request(
        self,
        task_id: str,
        reason: str,
        risk_factors: list[str],
        requested_by_user_id: int | None = None,
    ) -> HITLRequest:
        """Create a new HITL request.

        `requested_by_user_id` is de mens namens wie deze aanvraag ontstaat (ADR-036 OP-81). Hij
        komt uit de server-side `context` van `evaluate_task`, NOOIT uit een request body -- OWASP
        ASVS 5.0 8.3.1 eist handhaving in een trusted service layer op iets dat de consumer niet
        kan manipuleren. Zonder deze waarde blijft het veld leeg en slaat de zelf-goedkeuringscheck
        stroomafwaarts over; de rolcheck blijft dan de enige grens.
        """
        import uuid

        request_id = f"hitl_{uuid.uuid4().hex[:12]}"
        ticket_ref = f"TICKET-{uuid.uuid4().hex[:8].upper()}"

        return HITLRequest(
            request_id=request_id,
            task_id=task_id,
            tenant_id=self.tenant_id,
            reason=reason,
            risk_factors=risk_factors,
            requested_at=datetime.now(timezone.utc),
            ticket_ref=ticket_ref,
            requested_by_user_id=requested_by_user_id,
        )

    def approve_hitl_request(
        self, request_id: str, approved_by: str, notes: str | None = None
    ) -> bool:
        """Approve a pending HITL request."""
        if request_id not in self._hitl_requests:
            return False

        request = self._hitl_requests[request_id]
        if request.status != "pending":
            return False

        request.status = "approved"
        request.approved_by = approved_by
        request.approved_at = datetime.now(timezone.utc)

        logger.info(
            f"HITL request {request_id} approved by {approved_by}",
            extra={"ticket_ref": request.ticket_ref, "notes": notes},
        )

        return True

    def reject_hitl_request(self, request_id: str, rejected_by: str, reason: str) -> bool:
        """Reject a pending HITL request."""
        if request_id not in self._hitl_requests:
            return False

        request = self._hitl_requests[request_id]
        if request.status != "pending":
            return False

        request.status = "rejected"
        request.approved_by = rejected_by
        request.approved_at = datetime.now(timezone.utc)
        request.rejection_reason = reason

        logger.info(
            f"HITL request {request_id} rejected by {rejected_by}: {reason}",
            extra={"ticket_ref": request.ticket_ref},
        )

        return True

    def get_decision_log(
        self,
        task_id: str | None = None,
        decision_type: GateDecision | None = None,
        since: datetime | None = None,
    ) -> list[GateDecisionRecord]:
        """Get filtered decision log."""
        results = self._decision_log

        if task_id:
            results = [r for r in results if r.task_id == task_id]

        if decision_type:
            results = [r for r in results if r.decision == decision_type]

        if since:
            results = [r for r in results if r.timestamp >= since]

        return results

    def get_hitl_request(self, request_id: str) -> HITLRequest | None:
        """Get a HITL request by ID."""
        return self._hitl_requests.get(request_id)

    def get_hitl_requests_by_task(self, task_id: str) -> list[HITLRequest]:
        """Get all HITL requests for a task."""
        return [r for r in self._hitl_requests.values() if r.task_id == task_id]

    def get_statistics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get gatekeeper statistics."""
        total = len(self._decision_log)
        allowed = len([r for r in self._decision_log if r.decision == GateDecision.ALLOW])
        blocked = len([r for r in self._decision_log if r.decision == GateDecision.BLOCK])
        hitl = len([r for r in self._decision_log if r.decision == GateDecision.REQUIRE_HITL])

        pending_hitl = len([r for r in self._hitl_requests.values() if r.status == "pending"])
        approved_hitl = len([r for r in self._hitl_requests.values() if r.status == "approved"])
        rejected_hitl = len([r for r in self._hitl_requests.values() if r.status == "rejected"])

        return {
            "tenant_id": self.tenant_id,
            "total_decisions": total,
            "allowed": allowed,
            "blocked": blocked,
            "require_hitl": hitl,
            "hitl_pending": pending_hitl,
            "hitl_approved": approved_hitl,
            "hitl_rejected": rejected_hitl,
            "policy_rules_active": len([r for r in self._policy_rules.values() if r.enabled]),
        }
