"""
TKT-F4-01: Traceability Matrix PRD->Code->Tests

Maps requirements to code paths to tests to runtime evidence.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class CoverageStatus(Enum):
    """Coverage status for a requirement"""

    COVERED = "covered"  # Has implementation + tests
    PARTIAL = "partial"  # Has implementation, missing tests
    MISSING = "missing"  # No implementation
    DEPRECATED = "deprecated"  # No longer needed


class RequirementType(Enum):
    """Type of requirement"""

    FUNCTIONAL = "functional"
    SECURITY = "security"
    PERFORMANCE = "performance"
    COMPLIANCE = "compliance"


@dataclass
class Requirement:
    """A PRD requirement"""

    req_id: str
    description: str
    prd_section: str
    req_type: RequirementType
    priority: str  # must_have, should_have, nice_to_have

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "req_id": self.req_id,
            "description": self.description,
            "prd_section": self.prd_section,
            "type": self.req_type.value,
            "priority": self.priority,
        }


@dataclass
class Implementation:
    """Code implementation of a requirement"""

    req_id: str
    module_path: str
    class_name: str | None
    function_name: str
    lines_of_code: int
    complexity_score: int

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "req_id": self.req_id,
            "module_path": self.module_path,
            "class_name": self.class_name,
            "function_name": self.function_name,
            "lines_of_code": self.lines_of_code,
            "complexity_score": self.complexity_score,
        }


@dataclass
class TestEvidence:
    """Test evidence for a requirement"""

    req_id: str
    test_file: str
    test_function: str
    test_type: str  # unit, integration, e2e
    status: str  # passed, failed, skipped
    last_run: datetime
    execution_time_ms: float

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "req_id": self.req_id,
            "test_file": self.test_file,
            "test_function": self.test_function,
            "test_type": self.test_type,
            "status": self.status,
            "last_run": self.last_run.isoformat(),
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class RuntimeEvidence:
    """Runtime evidence that requirement works in production"""

    req_id: str
    event_type: str
    timestamp: datetime
    tenant_id: str
    success: bool
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class TraceabilityMatrix:
    """
    Complete traceability matrix from PRD requirements to code to tests.

    Usage:
        matrix = TraceabilityMatrix()

        # Register requirements from PRD
        matrix.add_requirement(Requirement(
            req_id="F0-01",
            description="Capability contract validation",
            prd_section="4.1",
            req_type=RequirementType.FUNCTIONAL,
            priority="must_have"
        ))

        # Link implementation
        matrix.link_implementation("F0-01", Implementation(...))

        # Link tests
        matrix.link_test("F0-01", TestEvidence(...))

        # Generate report
        report = matrix.generate_report()
        print(f"Coverage: {report.coverage_percentage}%")
    """

    def __init__(self) -> None:
        self._requirements: dict[str, Requirement] = {}
        self._implementations: dict[str, list[Implementation]] = {}
        self._tests: dict[str, list[TestEvidence]] = {}
        self._runtime_evidence: dict[str, list[RuntimeEvidence]] = {}

    def add_requirement(self, requirement: Requirement) -> None:
        """Add a PRD requirement"""
        self._requirements[requirement.req_id] = requirement
        self._implementations[requirement.req_id] = []
        self._tests[requirement.req_id] = []
        self._runtime_evidence[requirement.req_id] = []

    def link_implementation(self, req_id: str, implementation: Implementation) -> None:
        """Link code implementation to requirement"""
        if req_id not in self._implementations:
            self._implementations[req_id] = []
        self._implementations[req_id].append(implementation)

    def link_test(self, req_id: str, test: TestEvidence) -> None:
        """Link test evidence to requirement"""
        if req_id not in self._tests:
            self._tests[req_id] = []
        self._tests[req_id].append(test)

    def link_runtime_evidence(self, req_id: str, evidence: RuntimeEvidence) -> None:
        """Link runtime evidence to requirement"""
        if req_id not in self._runtime_evidence:
            self._runtime_evidence[req_id] = []
        self._runtime_evidence[req_id].append(evidence)

    def get_coverage_status(self, req_id: str) -> CoverageStatus:
        """Get coverage status for a requirement"""
        if req_id not in self._requirements:
            return CoverageStatus.MISSING

        has_impl = len(self._implementations.get(req_id, [])) > 0
        has_tests = len(self._tests.get(req_id, [])) > 0

        if has_impl and has_tests:
            return CoverageStatus.COVERED
        elif has_impl and not has_tests:
            return CoverageStatus.PARTIAL
        else:
            return CoverageStatus.MISSING

    def get_missing_requirements(self) -> list[str]:
        """Get list of requirements without implementation or tests"""
        missing: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for req_id in self._requirements:
            status = self.get_coverage_status(req_id)
            if status in [CoverageStatus.MISSING, CoverageStatus.PARTIAL]:
                missing.append(req_id)
        return missing

    def get_must_have_gaps(self) -> list[str]:
        """Get must-have requirements that are not fully covered"""
        gaps: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for req_id, req in self._requirements.items():
            if req.priority == "must_have":
                status = self.get_coverage_status(req_id)
                if status != CoverageStatus.COVERED:
                    gaps.append(req_id)
        return gaps

    def generate_report(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate traceability report"""
        total = len(self._requirements)
        covered = sum(
            1 for r in self._requirements if self.get_coverage_status(r) == CoverageStatus.COVERED
        )
        partial = sum(
            1 for r in self._requirements if self.get_coverage_status(r) == CoverageStatus.PARTIAL
        )
        missing = sum(
            1 for r in self._requirements if self.get_coverage_status(r) == CoverageStatus.MISSING
        )

        must_have_total = sum(1 for r in self._requirements.values() if r.priority == "must_have")
        must_have_covered = sum(
            1
            for req_id, req in self._requirements.items()
            if req.priority == "must_have"
            and self.get_coverage_status(req_id) == CoverageStatus.COVERED
        )

        return {
            "total_requirements": total,
            "covered": covered,
            "partial": partial,
            "missing": missing,
            "coverage_percentage": (covered / total * 100) if total > 0 else 0,
            "must_have": {
                "total": must_have_total,
                "covered": must_have_covered,
                "coverage_percentage": (
                    (must_have_covered / must_have_total * 100) if must_have_total > 0 else 0
                ),
            },
            "gaps": self.get_must_have_gaps(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def export_matrix(self, format_type: str = "json") -> str:
        """Export full traceability matrix"""
        data = {
            "requirements": {k: v.to_dict() for k, v in self._requirements.items()},
            "implementations": {
                k: [i.to_dict() for i in v] for k, v in self._implementations.items()
            },
            "tests": {k: [t.to_dict() for t in v] for k, v in self._tests.items()},
            "coverage": {
                req_id: self.get_coverage_status(req_id).value for req_id in self._requirements
            },
            "report": self.generate_report(),
        }

        if format_type == "json":
            return json.dumps(data, indent=2)
        elif format_type == "csv":
            # Simple CSV format
            lines = ["req_id,description,type,priority,status"]
            for req_id, req in self._requirements.items():
                status = self.get_coverage_status(req_id).value
                lines.append(
                    f'{req_id},"{req.description}",{req.req_type.value},{req.priority},{status}'
                )
            return "\n".join(lines)
        else:
            return json.dumps(data, indent=2)

    def load_prd_requirements(self) -> None:
        """Load all PRD v3.3 requirements"""
        # Fase 0 Requirements
        self.add_requirement(
            Requirement(
                "F0-01", "Capability Contract Core", "4.1", RequirementType.FUNCTIONAL, "must_have"
            )
        )
        self.add_requirement(
            Requirement(
                "F0-02", "Tenant Policy Enforcement", "4.2", RequirementType.FUNCTIONAL, "must_have"
            )
        )
        self.add_requirement(
            Requirement(
                "F0-03", "Execution Trace Contract", "4.3", RequirementType.FUNCTIONAL, "must_have"
            )
        )

        # Fase 1 Requirements
        self.add_requirement(
            Requirement(
                "F1-01",
                "D1 Template: Intake->Offerte->Review",
                "5.1",
                RequirementType.FUNCTIONAL,
                "must_have",
            )
        )
        self.add_requirement(
            Requirement(
                "F1-02",
                "D2 Template: Order->Fulfilment",
                "5.2",
                RequirementType.FUNCTIONAL,
                "must_have",
            )
        )
        self.add_requirement(
            Requirement(
                "F1-03",
                "D3 Template: Factuurcontrole->Approval",
                "5.3",
                RequirementType.FUNCTIONAL,
                "must_have",
            )
        )

        # Fase 2 Requirements
        self.add_requirement(
            Requirement(
                "F2-01",
                "Provider Resolver + Fallback",
                "6.1",
                RequirementType.FUNCTIONAL,
                "must_have",
            )
        )
        self.add_requirement(
            Requirement(
                "F2-02",
                "Notification Abstraction Layer",
                "6.2",
                RequirementType.FUNCTIONAL,
                "must_have",
            )
        )
        self.add_requirement(
            Requirement(
                "F2-03",
                "Builder Preflight Validation",
                "6.3",
                RequirementType.FUNCTIONAL,
                "must_have",
            )
        )

        # Fase 3 Requirements
        self.add_requirement(
            Requirement(
                "F3-01",
                "Intelligence Levels Enforcement",
                "7.1",
                RequirementType.FUNCTIONAL,
                "must_have",
            )
        )
        self.add_requirement(
            Requirement(
                "F3-02",
                "Compliance Route & Audit Bundle",
                "7.2",
                RequirementType.COMPLIANCE,
                "must_have",
            )
        )
        self.add_requirement(
            Requirement(
                "F3-03",
                "Starter/Growth/Pro Enforcement",
                "7.3",
                RequirementType.FUNCTIONAL,
                "must_have",
            )
        )

        # Security Requirements
        self.add_requirement(
            Requirement("SEC-01", "Tenant Isolation", "8.1", RequirementType.SECURITY, "must_have")
        )
        self.add_requirement(
            Requirement(
                "SEC-02", "Audit Trail Immutability", "8.2", RequirementType.SECURITY, "must_have"
            )
        )
        self.add_requirement(
            Requirement(
                "SEC-03", "Policy Violation Handling", "8.3", RequirementType.SECURITY, "must_have"
            )
        )
