"""
TKT-F2-03: Builder Preflight Contract Validation

Validates builder-generated flows before execution:
- Resolvable capabilities check
- Policy compliance check
- Trigger constraints check
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Type


class ValidationCheck(Enum):
    """Types of validation checks"""

    CAPABILITY_RESOLUTION = "capability_resolution"
    POLICY_COMPLIANCE = "policy_compliance"
    TRIGGER_CONSTRAINTS = "trigger_constraints"
    NODE_CONNECTIVITY = "node_connectivity"
    CIRCULAR_DEPENDENCY = "circular_dependency"


class ValidationSeverity(Enum):
    """Severity of validation issues"""

    ERROR = "error"  # Blocks execution
    WARNING = "warning"  # Allows execution with caution
    INFO = "info"  # Informational only


@dataclass
class ValidationIssue:
    """Individual validation issue"""

    check: ValidationCheck
    severity: ValidationSeverity
    node_id: str | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize to dictionary"""
        return {
            "check": self.check.value,
            "severity": self.severity.value,
            "node_id": self.node_id,
            "message": self.message,
            "details": self.details,
            "suggestion": self.suggestion,
        }


@dataclass
class PreflightResult:
    """Result of preflight validation"""

    workflow_id: str
    tenant_id: str
    can_execute: bool
    issues: list[ValidationIssue]
    validated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def has_errors(self) -> bool:
        """Check if there are blocking errors"""
        return any(i.severity == ValidationSeverity.ERROR for i in self.issues)

    def has_warnings(self) -> bool:
        """Check if there are warnings"""
        return any(i.severity == ValidationSeverity.WARNING for i in self.issues)

    def get_errors(self) -> list[ValidationIssue]:
        """Get all error-level issues"""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    def get_warnings(self) -> list[ValidationIssue]:
        """Get all warning-level issues"""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize to dictionary"""
        return {
            "workflow_id": self.workflow_id,
            "tenant_id": self.tenant_id,
            "can_execute": self.can_execute,
            "issues": [i.to_dict() for i in self.issues],
            "error_count": len(self.get_errors()),
            "warning_count": len(self.get_warnings()),
            "validated_at": self.validated_at.isoformat(),
        }


class PreflightValidator:
    """
    Validates workflow definitions before execution.

    Checks:
    1. All capabilities can be resolved
    2. Tenant policy allows the capabilities
    3. Trigger constraints are met
    4. Node connectivity is valid
    5. No circular dependencies

    Usage:
        validator = PreflightValidator()
        validator.register_capability("email.send")
        validator.set_tenant_policy(tenant_id, allowed_capabilities=["email.send"])

        result = validator.validate(workflow_def, tenant_id="tenant-123")
        if not result.can_execute:
            print("Cannot execute:", result.get_errors())
    """

    def __init__(self) -> None:
        self._capabilities: set[str] = set()
        self._tenant_policies: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self._trigger_constraints: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    def register_capability(self, capability_key: str) -> None:
        """Register an available capability"""
        self._capabilities.add(capability_key)

    def register_capabilities(self, capabilities: list[str]) -> None:
        """Register multiple capabilities"""
        self._capabilities.update(capabilities)

    def set_tenant_policy(self, tenant_id: str, allowed_capabilities: list[str]) -> None:
        """
        Set tenant policy for capability access.

        Args:
            tenant_id: Tenant identifier
            allowed_capabilities: List[Any] of allowed capability keys  # TODO(TYPE): replace Any with concrete type
        """
        self._tenant_policies[tenant_id] = {
            "allowed_capabilities": set(allowed_capabilities),
        }

    def set_trigger_constraint(self, trigger_type: str, required_fields: list[str]) -> None:
        """
        Set constraints for a trigger type.

        Args:
            trigger_type: Type of trigger (e.g., "webhook", "schedule")
            required_fields: Required configuration fields
        """
        self._trigger_constraints[trigger_type] = {
            "required_fields": required_fields,
        }

    def validate(
        self,
        workflow_def: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: str,
        workflow_id: str | None = None,
    ) -> PreflightResult:
        """
        Validate workflow definition.

        Args:
            workflow_def: Workflow definition (nodes, edges, trigger)
            tenant_id: Tenant identifier
            workflow_id: Optional workflow ID

        Returns:
            PreflightResult with validation issues
        """
        wf_id = workflow_id or workflow_def.get("workflow_id", "unknown")
        issues: list[ValidationIssue] = []

        # Extract workflow components
        nodes = workflow_def.get("nodes", [])
        edges = workflow_def.get("edges", [])
        trigger = workflow_def.get("trigger", {})

        # Run validation checks
        issues.extend(self._check_capabilities(nodes, tenant_id))
        issues.extend(self._check_policy_compliance(nodes, tenant_id))
        issues.extend(self._check_trigger_constraints(trigger))
        issues.extend(self._check_node_connectivity(nodes, edges))
        issues.extend(self._check_circular_dependencies(nodes, edges))

        # Determine if execution is allowed
        can_execute = not any(i.severity == ValidationSeverity.ERROR for i in issues)

        return PreflightResult(
            workflow_id=wf_id,
            tenant_id=tenant_id,
            can_execute=can_execute,
            issues=issues,
        )

    def _check_capabilities(
        self, nodes: list[dict[str, Any]], tenant_id: str  # TODO(TYPE): replace Any with concrete type
    ) -> list[ValidationIssue]:
        """Check if all node capabilities can be resolved"""
        issues: list[ValidationIssue] = []

        for node in nodes:
            node_id = node.get("id", "unknown")
            capability = node.get("capability") or node.get("capability_key")

            if not capability:
                issues.append(
                    ValidationIssue(
                        check=ValidationCheck.CAPABILITY_RESOLUTION,
                        severity=ValidationSeverity.ERROR,
                        node_id=node_id,
                        message="Node has no capability assigned",
                        details={"node_type": node.get("type")},
                        suggestion="Assign a capability to this node",
                    )
                )
                continue

            if capability not in self._capabilities:
                issues.append(
                    ValidationIssue(
                        check=ValidationCheck.CAPABILITY_RESOLUTION,
                        severity=ValidationSeverity.ERROR,
                        node_id=node_id,
                        message=f"Capability '{capability}' is not registered",
                        details={"capability": capability},
                        suggestion=f"Register capability '{capability}' or use an alternative",
                    )
                )

        return issues

    def _check_policy_compliance(
        self, nodes: list[dict[str, Any]], tenant_id: str  # TODO(TYPE): replace Any with concrete type
    ) -> list[ValidationIssue]:
        """Check if tenant policy allows the capabilities"""
        issues: list[ValidationIssue] = []

        policy = self._tenant_policies.get(tenant_id)
        if not policy:
            # No policy = allow all (in demo/development)
            return issues

        allowed = policy.get("allowed_capabilities", set())

        for node in nodes:
            node_id = node.get("id", "unknown")
            capability = node.get("capability") or node.get("capability_key")

            if capability and capability not in allowed:
                issues.append(
                    ValidationIssue(
                        check=ValidationCheck.POLICY_COMPLIANCE,
                        severity=ValidationSeverity.ERROR,
                        node_id=node_id,
                        message=f"Capability '{capability}' is not allowed for tenant '{tenant_id}'",
                        details={
                            "capability": capability,
                            "tenant_id": tenant_id,
                        },
                        suggestion="Contact administrator to enable this capability",
                    )
                )

        return issues

    def _check_trigger_constraints(self, trigger: dict[str, Any]) -> list[ValidationIssue]:  # TODO(TYPE): replace Any with concrete type
        """Check if trigger meets constraints"""
        issues: list[ValidationIssue] = []

        trigger_type = trigger.get("type")
        if not trigger_type:
            issues.append(
                ValidationIssue(
                    check=ValidationCheck.TRIGGER_CONSTRAINTS,
                    severity=ValidationSeverity.ERROR,
                    node_id=None,
                    message="Workflow has no trigger configured",
                    details={},
                    suggestion="Add a trigger to start the workflow",
                )
            )
            return issues

        constraints = self._trigger_constraints.get(trigger_type, {})
        required_fields = constraints.get("required_fields", [])
        config = trigger.get("config", {})

        for field_name in required_fields:
            if field_name not in config or config[field_name] is None:
                issues.append(
                    ValidationIssue(
                        check=ValidationCheck.TRIGGER_CONSTRAINTS,
                        severity=ValidationSeverity.ERROR,
                        node_id=None,
                        message=(f"Trigger '{trigger_type}' missing required field '{field_name}'"),
                        details={
                            "trigger_type": trigger_type,
                            "missing_field": field_name,
                        },
                        suggestion=f"Configure '{field_name}' in trigger settings",
                    )
                )

        return issues

    def _check_node_connectivity(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> list[ValidationIssue]:
        """Check if all nodes are properly connected"""
        issues: list[ValidationIssue] = []

        if not nodes:
            return issues

        node_ids = {n.get("id") for n in nodes if n.get("id")}

        # Check for isolated nodes (nodes with no edges)
        connected_nodes = set()
        for edge in edges:
            connected_nodes.add(edge.get("from"))
            connected_nodes.add(edge.get("to"))
            connected_nodes.add(edge.get("source"))  # Alternative naming
            connected_nodes.add(edge.get("target"))  # Alternative naming

        for node in nodes:
            node_id = node.get("id")
            if node_id and node_id not in connected_nodes:
                # Skip trigger nodes (they don't need incoming edges)
                if node.get("type") != "trigger":
                    issues.append(
                        ValidationIssue(
                            check=ValidationCheck.NODE_CONNECTIVITY,
                            severity=ValidationSeverity.WARNING,
                            node_id=node_id,
                            message=f"Node '{node_id}' is isolated (no connections)",
                            details={"node_id": node_id},
                            suggestion="Connect this node to the workflow",
                        )
                    )

        # Check for edges referencing non-existent nodes
        for edge in edges:
            from_node = edge.get("from") or edge.get("source")
            to_node = edge.get("to") or edge.get("target")

            if from_node and from_node not in node_ids:
                issues.append(
                    ValidationIssue(
                        check=ValidationCheck.NODE_CONNECTIVITY,
                        severity=ValidationSeverity.ERROR,
                        node_id=from_node,
                        message=f"Edge references non-existent node '{from_node}'",
                        details={"edge": edge},
                    )
                )

            if to_node and to_node not in node_ids:
                issues.append(
                    ValidationIssue(
                        check=ValidationCheck.NODE_CONNECTIVITY,
                        severity=ValidationSeverity.ERROR,
                        node_id=to_node,
                        message=f"Edge references non-existent node '{to_node}'",
                        details={"edge": edge},
                    )
                )

        return issues

    def _check_circular_dependencies(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> list[ValidationIssue]:
        """Check for circular dependencies in the graph"""
        issues: list[ValidationIssue] = []

        # Build adjacency list
        graph: dict[str, list[str]] = {}
        for node_data in nodes:
            node_id = node_data.get("id")
            if node_id:
                graph[node_id] = []

        for edge in edges:
            from_node = edge.get("from") or edge.get("source")
            to_node = edge.get("to") or edge.get("target")

            if from_node in graph and to_node:
                graph[from_node].append(to_node)

        # Detect cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node: str, path: list[str]) -> list[str] | None:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    cycle = has_cycle(neighbor, path + [neighbor])
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    # Found cycle
                    return path + [neighbor]

            rec_stack.remove(node)
            return None

        for graph_node in graph.keys():
            if graph_node not in visited:
                cycle = has_cycle(graph_node, [graph_node])
                if cycle:
                    issues.append(
                        ValidationIssue(
                            check=ValidationCheck.CIRCULAR_DEPENDENCY,
                            severity=ValidationSeverity.ERROR,
                            node_id=cycle[0],
                            message=f"Circular dependency detected: {' -> '.join(cycle)}",
                            details={"cycle": cycle},
                            suggestion="Remove circular references in workflow",
                        )
                    )
                    break  # Report first cycle only

        return issues
