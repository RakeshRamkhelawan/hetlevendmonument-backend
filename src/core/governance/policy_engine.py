from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class PolicyRiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ActionContext:
    action_name: str
    parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    risk_level: PolicyRiskLevel
    user_id: str | None = None
    tenant_id: str | None = None


@dataclass
class PolicyValidationResult:
    allowed: bool
    reason: str | None = None
    requires_approval: bool = False


@dataclass
class PolicyRule:
    """A single policy rule with priority support."""

    action_pattern: str  # Can be exact name or wildcard pattern (e.g., "query_*")
    allowed: bool
    reason: str | None = None
    requires_approval: bool = False
    priority: int = 100  # Higher number = higher priority (overrides lower)


class PolicyEngine:
    """
    Enforces governance rules on autonomous agent actions.

    DENY-BY-DEFAULT: All actions are denied unless explicitly allowed.
    This is a critical security feature to prevent unauthorized actions.

    Default ALLOW rules for safe operations:
    - query: Read-only data queries
    - analyze: Data analysis operations
    - respond: Response generation

    Agent entrypoint actions (see AGENT_ENTRYPOINT_ACTIONS below) are a separate,
    narrowly-scoped allow-list for top-level agent-dispatch verbs -- NOT the same
    contract as the read-only DEFAULT_ALLOW_ACTIONS above.

    Default DENY rules:
    - System file access
    - Private IP access
    - Unknown/unlisted actions

    Tenant-specific rules override defaults.
    """

    # Default ALLOW rules for safe standard operations (class constants)
    DEFAULT_ALLOW_ACTIONS: list[str] = [
        "query",
        "analyze",
        "respond",
        "search",
        "retrieve",
        "list",
        "get",
        "read",
    ]

    # Top-level agent-dispatch entry actions (class constant).
    #
    # SECURITY NOTE -- waarom dit veilig is:
    # Dit zijn de ENIGE namen die de outer governance-gate mogen passeren om een
    # agent-executiepad te MOGEN STARTEN. Ze zijn NIET destructief op zichzelf en
    # bevatten GEEN granulaire risicobeslissing. Elke concrete, potentieel gevaarlijke
    # sub-actie die BINNEN deze paden wordt uitgevoerd (bv. delete, write, deploy,
    # database_migration, permission_change) wordt APART en DIEPER in de pipeline
    # gegateerd via OversightGate.BREAKTHROUGH_ACTIONS en/of de EU AI Act
    # risk-classificatie (ai_act_classifier.classify_agent), die draaien op agent
    # department/specialisation/capabilities -- ONAFHANKELIJK van deze lijst.
    #
    # WAARSCHUWING VOOR TOEKOMSTIGE WIJZIGINGEN: voeg hier NOOIT een actienaam toe die
    # zelf een destructieve/schrijvende eindoperatie beschrijft (bv. "delete_*",
    # "execute_payment", "deploy_*"). Zie
    # tests/unit/test_policy_engine_architecture.py::test_agent_entrypoint_actions_no_destructive_verbs
    # die dit afdwingt. LET OP: die vangrail matcht alleen de substrings
    # delete/remove/drop/deploy/migrate/write/payment -- hij vervangt GEEN menselijke
    # afweging per naam. Elke toevoeging vereist een expliciet Rakesh-besluit; de
    # volledige, actuele scan van task_action-literals in src/ staat in
    # tests/unit/test_policy_engine_entrypoint_classification.py (SP-GOV-ENTRYPOINT-AUDIT).
    #
    # SP-GOV-ENTRYPOINT-AUDIT, besluit Rakesh 2026-07-31 (OP-11 dag 2): de zes namen
    # onder de streep zijn toegevoegd nadat ze stil deny-by-default werden geweigerd,
    # waardoor o.a. POST /api/v1/orchestrate/route en /critique in productie 403 gaven.
    AGENT_ENTRYPOINT_ACTIONS: list[str] = [
        "process_task",
        "orchestrate_task",
        "breakthrough_session",
        "execute_workflow",
        "create_and_execute",
        "stream_execution",
        "delegate_sub_task",
        # --- SP-GOV-ENTRYPOINT-AUDIT (2026-07-31) ---
        "route_task",  # read-only: kiest een agent, voert niets uit
        "critique_output",  # read-only: beoordeelt output, geeft score/issues
        "route_and_execute",  # dispatch; doelagent doet zijn eigen governance-check
        "execute_specialist",  # dispatch naar subagent, zelfde vorm als delegate_sub_task
        "start_swarm",  # dispatch met fan-out; budget/staplimiet volgt in ADR-036 Fase 2
        # RESTRISICO (bewust geaccepteerd, Rakesh 2026-07-31): dit is de enige actie die
        # start ZONDER menselijke trigger (src/core/agents/cva_autonomous_trigger.py),
        # terwijl de autonomie-ladder uit ADR-031 nog niet gewired is. De diepere poorten
        # blijven onverminderd gelden (AI Act-classificatie, BREAKTHROUGH_ACTIONS met
        # human approval, ShadowCEO-veto) -- deze lijst geeft alleen toegang tot het
        # STARTEN van een pad. Zie
        # tests/unit/test_policy_engine_entrypoint_classification.py::test_autonomous_breakthrough_deeper_gates_remain_intact
        "autonomous_breakthrough",
    ]

    # Default DENY patterns (class constants)
    DEFAULT_DENY_PATTERNS: dict[str, str] = {
        "file_system_access": "System file access is blocked by default",
        "network_access_private": "Private network access is blocked by default",
        "code_execution": "Arbitrary code execution is blocked by default",
        "shell_command": "Shell command execution is blocked by default",
    }

    # Blocked private IP patterns
    PRIVATE_IP_PATTERNS: list[str] = [
        "127.",
        "10.",
        "192.168.",
        "172.16.",
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",
        "169.254.",
        "0.0.0.0",  # nosec B104 - this is a blocklist entry for SSRF prevention, not a bind address
        "::1",
        "fc00:",
        "fe80:",
    ]

    def __init__(
        self,
        rules: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        tenant_rules: list[PolicyRule] | None = None,
    ) -> None:
        """
        Initialize policy engine.

        Args:
            rules: Legacy rules dict for backward compatibility
            tenant_rules: Tenant-specific policy rules (override defaults)
        """
        self.rules = rules or {}
        self.tenant_rules = tenant_rules or []

    async def validate_action(self, context: ActionContext) -> PolicyValidationResult:
        """
        Validates whether an action is allowed, blocked, or requires approval.

        Evaluation order (highest priority first):
        1. Tenant-specific rules (if any)
        2. Blocked domains/URLs
        3. Private IP blocking
        4. System file access blocking
        5. Require-approval actions / CRITICAL risk
        6. Agent entrypoint dispatch actions (AGENT_ENTRYPOINT_ACTIONS)
        7. Default allow list (query, analyze, respond)
        8. Default DENY (if no rule matched)

        Returns:
            PolicyValidationResult with allowed status and reason
        """
        action_name = context.action_name
        parameters = context.parameters

        # 1. Check tenant-specific rules first (highest priority)
        if self.tenant_rules:
            # Sort by priority (highest first)
            sorted_rules = sorted(self.tenant_rules, key=lambda r: r.priority, reverse=True)
            for rule in sorted_rules:
                if self._matches_action(rule.action_pattern, action_name):
                    return PolicyValidationResult(
                        allowed=rule.allowed,
                        reason=rule.reason,
                        requires_approval=rule.requires_approval,
                    )

        # 2. Check for Blocked Domains (if applicable)
        if "url" in parameters:
            url = parameters["url"]

            # Check blocked domains
            blocked_domains = self.rules.get("blocked_domains", [])
            for domain in blocked_domains:
                if domain in url:
                    return PolicyValidationResult(
                        allowed=False, reason=f"Domain '{domain}' is blocked."
                    )

            # Check for private IP blocking
            if self._is_private_ip(url):
                return PolicyValidationResult(
                    allowed=False, reason="Access to private IP addresses is blocked."
                )

        # 3. Check for system file access
        if "path" in parameters:
            path = parameters["path"]
            if self._is_system_path(path):
                return PolicyValidationResult(
                    allowed=False,
                    reason="Access to system paths is blocked by default.",
                )

        # 5. Check for high-risk operations requiring approval
        require_approval_actions = self.rules.get("require_approval_actions", [])

        if (action_name in require_approval_actions) or (
            context.risk_level == PolicyRiskLevel.CRITICAL
        ):
            return PolicyValidationResult(
                allowed=True,  # Allowed but requires approval
                requires_approval=True,
                reason=f"Manual approval required for action '{action_name}'",
            )

        # 6. Check agent entrypoint dispatch actions (outer dispatch gate only --
        #    does not grant any sub-action rights; see AGENT_ENTRYPOINT_ACTIONS docstring)
        if action_name in self.AGENT_ENTRYPOINT_ACTIONS:
            return PolicyValidationResult(
                allowed=True,
                reason=f"Action '{action_name}' is a recognised agent entrypoint action.",
            )

        # 7. Check default allow list for safe operations
        if action_name in self.DEFAULT_ALLOW_ACTIONS:
            return PolicyValidationResult(
                allowed=True, reason=f"Action '{action_name}' is in default allow list."
            )

        # 8. DENY-BY-DEFAULT: Unknown/unlisted actions are denied
        return PolicyValidationResult(
            allowed=False,
            reason=f"Action '{action_name}' is denied by default. Not in allowed actions list.",
        )

    def _matches_action(self, pattern: str, action_name: str) -> bool:
        """Check if action name matches pattern (supports wildcards)."""
        if pattern == action_name:
            return True
        if pattern.endswith("*"):
            return action_name.startswith(pattern[:-1])
        if pattern.startswith("*"):
            return action_name.endswith(pattern[1:])
        return False

    def _is_private_ip(self, url: str) -> bool:
        """Check if URL contains a private IP address."""
        url_lower = url.lower()
        for pattern in self.PRIVATE_IP_PATTERNS:
            if pattern in url_lower:
                return True
        return False

    def _is_system_path(self, path: str) -> bool:
        """Check if path is a system path."""
        system_paths = [
            "/etc/",
            "/usr/bin/",
            "/bin/",
            "/sbin/",
            "/boot/",
            "/sys/",
            "/proc/",
            "/dev/",
            "/var/log/",
            "C:\\Windows\\",
            "C:\\Program Files\\",
            "C:\\System",
            "../",
            "..\\",  # Path traversal attempts
        ]
        path_lower = path.lower()
        for sys_path in system_paths:
            if sys_path.lower() in path_lower:
                return True
        return False

    def add_tenant_rule(self, rule: PolicyRule) -> None:
        """Add a tenant-specific rule."""
        self.tenant_rules.append(rule)

    def get_default_allow_actions(self) -> list[str]:
        """Get the list of default allowed actions."""
        return self.DEFAULT_ALLOW_ACTIONS.copy()

    def get_agent_entrypoint_actions(self) -> list[str]:
        """Get the list of recognised agent entrypoint dispatch actions."""
        return self.AGENT_ENTRYPOINT_ACTIONS.copy()

    def get_default_deny_patterns(self) -> dict[str, str]:
        """Get the default deny patterns."""
        return self.DEFAULT_DENY_PATTERNS.copy()
