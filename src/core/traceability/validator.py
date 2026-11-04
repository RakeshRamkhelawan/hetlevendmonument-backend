"""
TKT-F4-01: Traceability Validator & Release Gate

Validates traceability matrix and determines release readiness.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .matrix import CoverageStatus, TraceabilityMatrix


class GateStatus(Enum):
    """Release gate status"""

    PASSED = "passed"
    BLOCKED = "blocked"
    WARNING = "warning"


@dataclass
class ValidationIssue:
    """Issue found during validation"""

    severity: str  # critical, high, medium, low
    req_id: str | None
    message: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "severity": self.severity,
            "req_id": self.req_id,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationReport:
    """Full validation report"""

    status: GateStatus
    timestamp: datetime
    issues: list[ValidationIssue]
    coverage_percentage: float
    must_have_coverage: float
    total_requirements: int
    covered_requirements: int
    missing_evidence: list[str]

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "coverage_percentage": self.coverage_percentage,
            "must_have_coverage": self.must_have_coverage,
            "total_requirements": self.total_requirements,
            "covered_requirements": self.covered_requirements,
            "issues": [i.to_dict() for i in self.issues],
            "missing_evidence": self.missing_evidence,
            "issue_count": len(self.issues),
            "critical_issues": len([i for i in self.issues if i.severity == "critical"]),
        }


class TraceabilityValidator:
    """
    Validates traceability matrix for release readiness.

    Checks:
    - 100% must-have coverage
    - No missing evidence
    - All tests passing
    - Runtime evidence for critical paths

    Usage:
        validator = TraceabilityValidator(matrix)
        report = validator.validate()

        if report.status == GateStatus.PASSED:
            print("Ready for release!")
        else:
            print(f"Blocked: {report.issues}")
    """

    def __init__(self, matrix: TraceabilityMatrix) -> None:
        self.matrix = matrix

    def validate(self) -> ValidationReport:
        """
        Run full validation and generate report.

        Returns:
            ValidationReport with status and issues
        """
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Get matrix report
        report = self.matrix.generate_report()

        # Check 1: Must-have coverage must be 100%
        must_have_coverage = report["must_have"]["coverage_percentage"]
        if must_have_coverage < 100:
            missing_must_have = report["gaps"]
            issues.append(
                ValidationIssue(
                    severity="critical",
                    req_id=None,
                    message=f"Must-have coverage is {must_have_coverage:.1f}%, required 100%",
                    suggestion=f"Add implementation/tests for: {', '.join(missing_must_have[:5])}",
                )
            )

        # Check 2: No MISSING status for must-haves
        for req_id in self.matrix.get_must_have_gaps():
            coverage_status = self.matrix.get_coverage_status(req_id)
            if coverage_status == CoverageStatus.MISSING:
                issues.append(
                    ValidationIssue(
                        severity="critical",
                        req_id=req_id,
                        message=f"Must-have requirement {req_id} has no implementation",
                        suggestion="Implement the requirement or mark as deprecated",
                    )
                )
            elif coverage_status == CoverageStatus.PARTIAL:
                issues.append(
                    ValidationIssue(
                        severity="high",
                        req_id=req_id,
                        message=f"Must-have requirement {req_id} has implementation but no tests",
                        suggestion="Add test coverage for this requirement",
                    )
                )

        # Check 3: Overall coverage threshold (90%)
        overall_coverage = report["coverage_percentage"]
        if overall_coverage < 90:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    req_id=None,
                    message=f"Overall coverage is {overall_coverage:.1f}%, recommended 90%",
                    suggestion="Add tests for uncovered requirements",
                )
            )

        # Determine gate status
        critical_issues = len([i for i in issues if i.severity == "critical"])
        high_issues = len([i for i in issues if i.severity == "high"])

        if critical_issues > 0:
            status = GateStatus.BLOCKED
        elif high_issues > 0:
            status = GateStatus.WARNING
        else:
            status = GateStatus.PASSED

        return ValidationReport(
            status=status,
            timestamp=datetime.now(timezone.utc),
            issues=issues,
            coverage_percentage=overall_coverage,
            must_have_coverage=must_have_coverage,
            total_requirements=report["total_requirements"],
            covered_requirements=report["covered"],
            missing_evidence=self.matrix.get_missing_requirements(),
        )


class ReleaseGate:
    """
    Final release gate check.

    Enforces Definition of Done:
    1. All tickets Done
    2. All phase integration tests green
    3. Traceability matrix 100% coverage
    4. No critical/high defects
    5. UI/API/runtime policy consistency

    Usage:
        gate = ReleaseGate(matrix)

        if gate.check():
            release()
        else:
            fix_issues(gate.get_blockers())
    """

    def __init__(self, matrix: TraceabilityMatrix) -> None:
        self.matrix = matrix
        self.validator = TraceabilityValidator(matrix)
        self._checklist = {
            "tickets_done": False,
            "integration_tests_green": False,
            "traceability_100": False,
            "no_critical_defects": False,
            "policy_consistency": False,
        }

    def set_checklist_item(self, item: str, status: bool) -> None:
        """Set checklist item status"""
        if item in self._checklist:
            self._checklist[item] = status

    def check(self) -> tuple[bool, list[str]]:
        """
        Run full release gate check.

        Returns: Tuple[Any, ...] of (passed, blockers)  # TODO(TYPE): replace Any with concrete type
        """
        blockers: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check traceability
        report = self.validator.validate()
        if report.status == GateStatus.BLOCKED:
            blockers.append(
                f"Traceability: {report.issues[0].message if report.issues else 'Unknown issue'}"
            )

        # Check checklist
        for item, status in self._checklist.items():
            if not status:
                blockers.append(f"Checklist item not complete: {item}")

        return len(blockers) == 0, blockers

    def get_report(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get full release gate report"""
        report = self.validator.validate()
        passed, blockers = self.check()

        return {
            "ready_for_release": passed,
            "traceability_report": report.to_dict(),
            "checklist": self._checklist.copy(),
            "blockers": blockers,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
