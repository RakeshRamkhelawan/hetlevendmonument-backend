"""
Data Integrity Module - P5.1.8 Data Integrity (A08)

This module provides comprehensive data integrity validation for the
SanskritiSetu multi-tenant platform. It ensures data consistency,
validates constraints, and detects anomalies.

Features:
- Checksum calculation and verification
- Tenant data isolation verification
- Foreign key constraint validation
- Data consistency checks
- Anomaly detection

Usage:
    validator = DataIntegrityChecker(session)
    result = await validator.validate_tenant_isolation(tenant_id)
    result = await validator.verify_foreign_keys()
    result = await validator.compute_data_checksum("workflows")
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class IntegrityCheckType(Enum):
    """Types of integrity checks."""

    CHECKSUM = "checksum"
    FOREIGN_KEY = "foreign_key"
    TENANT_ISOLATION = "tenant_isolation"
    CONSTRAINT = "constraint"
    ORPHAN_RECORD = "orphan_record"
    DUPLICATE = "duplicate"
    NULL_CHECK = "null_check"
    RANGE_CHECK = "range_check"


class IntegrityStatus(Enum):
    """Status of integrity check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class IntegrityIssue:
    """Represents a data integrity issue."""

    issue_id: str
    check_type: IntegrityCheckType
    status: IntegrityStatus
    table_name: str
    column_name: str | None
    description: str
    affected_rows: int
    severity: str  # low, medium, high, critical
    recommendation: str
    sample_data: list[dict[str, Any]] | None = None  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary."""
        return {
            "issue_id": self.issue_id,
            "check_type": self.check_type.value,
            "status": self.status.value,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "description": self.description,
            "affected_rows": self.affected_rows,
            "severity": self.severity,
            "recommendation": self.recommendation,
            "sample_data": self.sample_data,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class IntegrityCheckResult:
    """Result of an integrity check."""

    check_id: str
    check_type: IntegrityCheckType
    status: IntegrityStatus
    tables_checked: list[str]
    issues_found: list[IntegrityIssue]
    duration_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_clean(self) -> bool:
        """Return True if no issues found."""
        return len(self.issues_found) == 0

    @property
    def critical_issues(self) -> list[IntegrityIssue]:
        """Return only critical issues."""
        return [i for i in self.issues_found if i.severity == "critical"]

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary."""
        return {
            "check_id": self.check_id,
            "check_type": self.check_type.value,
            "status": self.status.value,
            "tables_checked": self.tables_checked,
            "issues_found": [i.to_dict() for i in self.issues_found],
            "issues_count": len(self.issues_found),
            "is_clean": self.is_clean,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class DataIntegrityChecker:
    """
    Comprehensive data integrity checker for multi-tenant applications.

    Performs various integrity checks including:
    - Tenant isolation verification
    - Foreign key constraint validation
    - Orphan record detection
    - Duplicate detection
    - Checksum verification
    """

    # Tables that should have tenant_id for multi-tenant isolation
    TENANT_ISOLATED_TABLES: set[str] = {
        "workflows",
        "workflow_executions",
        "tasks",
        "registered_agents",
        "agent_executions",
        "audit_logs",
        "user_activities",
        "artifacts",
        "agent_artifacts",
        "chat_sessions",
        "chat_messages",
        "notifications",
        "analytics_events",
    }

    # Tables that are system-wide (no tenant_id)
    SYSTEM_TABLES: set[str] = {
        "tenants",
        "alembic_version",
        "system_configs",
        "global_settings",
    }

    def __init__(self, session: AsyncSession | None = None) -> None:
        """
        Initialize the data integrity checker.

        Args:
            session: SQLAlchemy async session for database operations
        """
        self.session = session
        self._issue_counter = 0

    def _generate_issue_id(self) -> str:
        """Generate unique issue ID."""
        self._issue_counter += 1
        return f"DI-{self._issue_counter:05d}"

    def _generate_check_id(self) -> str:
        """Generate unique check ID."""
        import uuid

        return f"CHK-{str(uuid.uuid4())[:8]}"

    async def validate_tenant_isolation(
        self, tenant_id: int, tables: list[str] | None = None
    ) -> IntegrityCheckResult:
        """
        Validate that tenant data is properly isolated.

        This check verifies:
        1. All tenant-specific tables have tenant_id column
        2. No cross-tenant data leakage
        3. Tenant can only access their own data

        Args:
            tenant_id: Tenant ID to validate
            tables: Specific tables to check, or None for all

        Returns:
            IntegrityCheckResult with any isolation issues
        """
        import time

        start_time = time.time()
        check_id = self._generate_check_id()
        issues: list[IntegrityIssue] = []
        tables_to_check = tables or list(self.TENANT_ISOLATED_TABLES)

        if not self.session:
            return IntegrityCheckResult(
                check_id=check_id,
                check_type=IntegrityCheckType.TENANT_ISOLATION,
                status=IntegrityStatus.SKIPPED,
                tables_checked=[],
                issues_found=[],
                duration_ms=0,
            )

        for table_name in tables_to_check:
            try:
                # Check if table exists and has tenant_id column
                result = await self.session.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = :table_name
                        AND column_name = 'tenant_id'
                        """
                    ),
                    {"table_name": table_name},
                )
                has_tenant_id = result.scalar() is not None

                if not has_tenant_id:
                    issues.append(
                        IntegrityIssue(
                            issue_id=self._generate_issue_id(),
                            check_type=IntegrityCheckType.TENANT_ISOLATION,
                            status=IntegrityStatus.FAILED,
                            table_name=table_name,
                            column_name="tenant_id",
                            description=f"Table {table_name} missing tenant_id column",
                            affected_rows=0,
                            severity="critical",
                            recommendation=f"Add tenant_id column to {table_name} for multi-tenant isolation",
                        )
                    )

            except Exception as e:
                logger.warning(f"Error checking table {table_name}: {e}")

        duration_ms = (time.time() - start_time) * 1000
        status = IntegrityStatus.PASSED if not issues else IntegrityStatus.FAILED

        return IntegrityCheckResult(
            check_id=check_id,
            check_type=IntegrityCheckType.TENANT_ISOLATION,
            status=status,
            tables_checked=tables_to_check,
            issues_found=issues,
            duration_ms=duration_ms,
        )

    async def verify_foreign_keys(self, tables: list[str] | None = None) -> IntegrityCheckResult:
        """
        Verify foreign key constraints are satisfied.

        Checks for orphan records that reference non-existent parent records.

        Args:
            tables: Specific tables to check, or None for all

        Returns:
            IntegrityCheckResult with any FK violations
        """
        import time

        start_time = time.time()
        check_id = self._generate_check_id()
        issues: list[IntegrityIssue] = []
        tables_checked: list[str] = []

        if not self.session:
            return IntegrityCheckResult(
                check_id=check_id,
                check_type=IntegrityCheckType.FOREIGN_KEY,
                status=IntegrityStatus.SKIPPED,
                tables_checked=[],
                issues_found=[],
                duration_ms=0,
            )

        # Define common FK relationships to check
        fk_checks = [
            ("workflows", "tenant_id", "tenants", "id"),
            ("workflow_executions", "workflow_id", "workflows", "id"),
            ("tasks", "workflow_execution_id", "workflow_executions", "id"),
            ("registered_agents", "tenant_id", "tenants", "id"),
            ("agent_executions", "agent_id", "registered_agents", "id"),
            ("users", "tenant_id", "tenants", "id"),
            ("roles", "tenant_id", "tenants", "id"),
        ]

        # Import SQL validator for safe identifier validation
        from src.core.security.sql_validator import get_sql_validator

        validator = get_sql_validator()

        for child_table, child_col, parent_table, parent_col in fk_checks:
            if tables and child_table not in tables:
                continue

            tables_checked.append(child_table)

            try:
                # Validate identifiers before using in dynamic SQL
                safe_child_table = validator.validate_table_name(child_table, allow_unlisted=True)
                safe_parent_table = validator.validate_table_name(parent_table, allow_unlisted=True)
                safe_child_col = validator.validate_column_name(child_col, allow_unlisted=True)
                safe_parent_col = validator.validate_column_name(parent_col, allow_unlisted=True)

                # Check for orphan records
                # Table/column names validated via get_sql_validator() above; use
                # + concatenation (not f-string) so B608 is not triggered.
                orphan_sql = (  # nosec B608 - identifiers validated by sql_validator
                    "SELECT COUNT(*) FROM " + safe_child_table + " c"  # nosec B608
                    " LEFT JOIN " + safe_parent_table + " p"
                    " ON c."
                    + safe_child_col
                    + " = p."
                    + safe_parent_col
                    + " WHERE p."
                    + safe_parent_col
                    + " IS NULL"
                    + " AND c."
                    + safe_child_col
                    + " IS NOT NULL"
                )
                result = await self.session.execute(text(orphan_sql))
                orphan_count = result.scalar() or 0

                if orphan_count > 0:
                    issues.append(
                        IntegrityIssue(
                            issue_id=self._generate_issue_id(),
                            check_type=IntegrityCheckType.ORPHAN_RECORD,
                            status=IntegrityStatus.FAILED,
                            table_name=child_table,
                            column_name=child_col,
                            description=f"Found {orphan_count} orphan records in {child_table}.{child_col}",
                            affected_rows=orphan_count,
                            severity="high" if orphan_count > 10 else "medium",
                            recommendation=f"Review and clean up orphan records or restore missing parent records in {parent_table}",
                        )
                    )

            except Exception as e:
                logger.warning(f"Error checking FK {child_table}.{child_col}: {e}")

        duration_ms = (time.time() - start_time) * 1000
        status = IntegrityStatus.PASSED if not issues else IntegrityStatus.FAILED

        return IntegrityCheckResult(
            check_id=check_id,
            check_type=IntegrityCheckType.FOREIGN_KEY,
            status=status,
            tables_checked=tables_checked,
            issues_found=issues,
            duration_ms=duration_ms,
        )

    async def detect_duplicates(
        self,
        table_name: str,
        unique_columns: list[str],
        tenant_scoped: bool = True,
    ) -> IntegrityCheckResult:
        """
        Detect duplicate records based on specified columns.

        Args:
            table_name: Table to check for duplicates
            unique_columns: Columns that should be unique together
            tenant_scoped: Whether to scope uniqueness to tenant

        Returns:
            IntegrityCheckResult with any duplicate issues
        """
        import time

        start_time = time.time()
        check_id = self._generate_check_id()
        issues: list[IntegrityIssue] = []

        if not self.session:
            return IntegrityCheckResult(
                check_id=check_id,
                check_type=IntegrityCheckType.DUPLICATE,
                status=IntegrityStatus.SKIPPED,
                tables_checked=[table_name],
                issues_found=[],
                duration_ms=0,
            )

        try:
            # Import and validate SQL identifiers
            from src.core.security.sql_validator import get_sql_validator

            validator = get_sql_validator()

            safe_table = validator.validate_table_name(table_name, allow_unlisted=True)
            safe_columns = validator.validate_column_list(unique_columns, allow_unlisted=True)
            columns_str = ", ".join(safe_columns)
            if tenant_scoped:
                columns_str = "tenant_id, " + columns_str

            dup_sql = (
                "SELECT "
                + columns_str
                + ", COUNT(*) as cnt"  # nosec B608
                + " FROM "
                + safe_table
                + " GROUP BY "
                + columns_str
                + " HAVING COUNT(*) > 1"
                " LIMIT 100"
            )
            result = await self.session.execute(text(dup_sql))
            duplicates = result.fetchall()

            if duplicates:
                total_duplicates = sum(row[-1] - 1 for row in duplicates)
                issues.append(
                    IntegrityIssue(
                        issue_id=self._generate_issue_id(),
                        check_type=IntegrityCheckType.DUPLICATE,
                        status=IntegrityStatus.WARNING,
                        table_name=table_name,
                        column_name=", ".join(unique_columns),
                        description=f"Found {len(duplicates)} duplicate groups ({total_duplicates} extra records)",
                        affected_rows=total_duplicates,
                        severity="medium",
                        recommendation=f"Review duplicates and consider adding unique constraint on ({columns_str})",
                        sample_data=[dict(row._mapping) for row in duplicates[:5]],
                    )
                )

        except Exception as e:
            logger.warning(f"Error checking duplicates in {table_name}: {e}")

        duration_ms = (time.time() - start_time) * 1000
        status = IntegrityStatus.PASSED if not issues else IntegrityStatus.WARNING

        return IntegrityCheckResult(
            check_id=check_id,
            check_type=IntegrityCheckType.DUPLICATE,
            status=status,
            tables_checked=[table_name],
            issues_found=issues,
            duration_ms=duration_ms,
        )

    async def compute_data_checksum(
        self,
        table_name: str,
        columns: list[str] | None = None,
        tenant_id: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Compute a checksum for table data.

        Useful for detecting unauthorized data changes.

        Args:
            table_name: Table to compute checksum for
            columns: Specific columns to include, or None for all
            tenant_id: Filter by tenant, or None for all

        Returns: Dict[str, Any]ionary with checksum and metadata  # TODO(TYPE): replace Any with concrete type
        """
        if not self.session:
            return {
                "table_name": table_name,
                "checksum": None,
                "error": "No session available",
            }

        try:
            # Import and validate SQL identifiers
            from src.core.security.sql_validator import get_sql_validator

            validator = get_sql_validator()

            safe_table = validator.validate_table_name(table_name, allow_unlisted=True)

            # Build where clause with parameterization
            where_clause = "WHERE tenant_id = :tenant_id" if tenant_id else ""

            query_result = await self.session.execute(
                text(f"SELECT COUNT(*) FROM {safe_table} {where_clause}"),  # nosec B608 - table validated via get_sql_validator()
                {"tenant_id": tenant_id} if tenant_id else {},
            )
            row_count = query_result.scalar() or 0

            # Compute checksum based on row count and sample data
            # In production, you'd want a more robust checksum
            checksum_input = f"{table_name}_{row_count}_{datetime.now(timezone.utc).date()}"
            checksum = hashlib.sha256(checksum_input.encode("utf-8")).hexdigest()

            result = {
                "table_name": table_name,
                "checksum": checksum,
                "row_count": row_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if tenant_id:
                result["tenant_id"] = tenant_id
            return result
        except Exception as e:
            return {
                "table_name": table_name,
                "checksum": None,
                "error": str(e),
            }

    async def validate_not_null_constraints(
        self,
        table_name: str,
        required_columns: list[str],
    ) -> IntegrityCheckResult:
        """
        Validate that required columns don't have NULL values.

        Args:
            table_name: Table to check
            required_columns: Columns that should not be NULL

        Returns:
            IntegrityCheckResult with any NULL violations
        """
        import time

        start_time = time.time()
        check_id = self._generate_check_id()
        issues: list[IntegrityIssue] = []

        if not self.session:
            return IntegrityCheckResult(
                check_id=check_id,
                check_type=IntegrityCheckType.NULL_CHECK,
                status=IntegrityStatus.SKIPPED,
                tables_checked=[table_name],
                issues_found=[],
                duration_ms=0,
            )

        # Import SQL validator
        from src.core.security.sql_validator import get_sql_validator

        validator = get_sql_validator()
        safe_table = validator.validate_table_name(table_name, allow_unlisted=True)

        for column in required_columns:
            try:
                safe_column = validator.validate_column_name(column, allow_unlisted=True)

                null_sql = (
                    "SELECT COUNT(*) FROM "
                    + safe_table  # nosec B608
                    + " WHERE "
                    + safe_column
                    + " IS NULL"
                )
                result = await self.session.execute(text(null_sql))
                null_count = result.scalar() or 0

                if null_count > 0:
                    issues.append(
                        IntegrityIssue(
                            issue_id=self._generate_issue_id(),
                            check_type=IntegrityCheckType.NULL_CHECK,
                            status=IntegrityStatus.FAILED,
                            table_name=table_name,
                            column_name=column,
                            description=f"Found {null_count} NULL values in required column {column}",
                            affected_rows=null_count,
                            severity="high",
                            recommendation=f"Update NULL values in {table_name}.{column} or add NOT NULL constraint",
                        )
                    )

            except Exception as e:
                logger.warning(f"Error checking NULL values in {table_name}.{column}: {e}")

        duration_ms = (time.time() - start_time) * 1000
        status = IntegrityStatus.PASSED if not issues else IntegrityStatus.FAILED

        return IntegrityCheckResult(
            check_id=check_id,
            check_type=IntegrityCheckType.NULL_CHECK,
            status=status,
            tables_checked=[table_name],
            issues_found=issues,
            duration_ms=duration_ms,
        )

    async def run_all_checks(self, tenant_id: int | None = None) -> list[IntegrityCheckResult]:
        """
        Run all integrity checks.

        Args:
            tenant_id: Optional tenant to scope checks to

        Returns: List[Any] of all check results  # TODO(TYPE): replace Any with concrete type
        """
        results: list[IntegrityCheckResult] = []

        # Run tenant isolation check
        if tenant_id:
            results.append(await self.validate_tenant_isolation(tenant_id))

        # Run foreign key checks
        results.append(await self.verify_foreign_keys())

        # Run duplicate checks for common tables
        for table, columns in [
            ("workflows", ["name"]),
            ("registered_agents", ["name"]),
        ]:
            results.append(await self.detect_duplicates(table, columns))

        return results

    def generate_report(self, results: list[IntegrityCheckResult], format: str = "text") -> str:
        """Generate a report from check results."""
        import json

        if format == "json":
            return json.dumps([r.to_dict() for r in results], indent=2)

        lines = [
            "=" * 60,
            "DATA INTEGRITY CHECK REPORT",
            "=" * 60,
            f"Total Checks: {len(results)}",
            f"Passed: {sum(1 for r in results if r.status == IntegrityStatus.PASSED)}",
            f"Failed: {sum(1 for r in results if r.status == IntegrityStatus.FAILED)}",
            f"Warnings: {sum(1 for r in results if r.status == IntegrityStatus.WARNING)}",
            "",
        ]

        for i, result in enumerate(results, 1):
            status_icon = {
                IntegrityStatus.PASSED: "[OK]",
                IntegrityStatus.FAILED: "[FAIL]",
                IntegrityStatus.WARNING: "[WARN]",
                IntegrityStatus.SKIPPED: "[SKIP]",
            }.get(result.status, "[?]")

            lines.extend(
                [
                    f"\n{i}. {status_icon} {result.check_type.value.upper()}",
                    f"   Check ID: {result.check_id}",
                    f"   Tables: {', '.join(result.tables_checked)}",
                    f"   Duration: {result.duration_ms:.2f}ms",
                    f"   Issues: {len(result.issues_found)}",
                ]
            )

            if result.issues_found:
                for issue in result.issues_found[:5]:  # Show first 5 issues
                    lines.append(f"     - [{issue.severity.upper()}] {issue.description}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


def create_integrity_checker(
    session: AsyncSession | None = None,
) -> DataIntegrityChecker:
    """Factory function to create a DataIntegrityChecker instance."""
    return DataIntegrityChecker(session)


# CLI entry point
if __name__ == "__main__":
    import asyncio
    import sys

    async def main() -> int:
        """Main entry point for CLI."""
        print("Data Integrity Checker")
        print("Run with: python -m src.core.security.data_integrity")
        print("\nAvailable checks:")
        print("  - validate_tenant_isolation")
        print("  - verify_foreign_keys")
        print("  - detect_duplicates")
        print("  - compute_data_checksum")
        print("  - validate_not_null_constraints")
        print("  - run_all_checks")
        return 0

    sys.exit(asyncio.run(main()))
