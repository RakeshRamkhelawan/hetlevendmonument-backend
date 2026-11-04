"""
Unit tests for P5.1.8 - Data Integrity (A08): Data Integrity Checker

Tests the data integrity validation functionality for multi-tenant
applications including tenant isolation, foreign keys, and checksums.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.security.data_integrity import (
    DataIntegrityChecker,
    IntegrityCheckResult,
    IntegrityCheckType,
    IntegrityIssue,
    IntegrityStatus,
    create_integrity_checker,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def checker() -> DataIntegrityChecker:
    """Create a DataIntegrityChecker instance without session."""
    return DataIntegrityChecker(session=None)


@pytest.fixture
def checker_with_session(mock_session: AsyncMock) -> DataIntegrityChecker:
    """Create a DataIntegrityChecker instance with mock session."""
    return DataIntegrityChecker(session=mock_session)


class TestDataIntegrityChecker:
    """Test suite for DataIntegrityChecker class."""

    def test_checker_initialization_without_session(self):
        """Test checker initializes without session."""
        checker = DataIntegrityChecker()
        assert checker is not None
        assert checker.session is None

    def test_checker_initialization_with_session(self, mock_session: AsyncMock):
        """Test checker initializes with session."""
        checker = DataIntegrityChecker(session=mock_session)
        assert checker is not None
        assert checker.session == mock_session

    def test_generate_issue_id(self, checker: DataIntegrityChecker):
        """Test issue ID generation is unique."""
        id1 = checker._generate_issue_id()
        id2 = checker._generate_issue_id()
        id3 = checker._generate_issue_id()

        assert id1 != id2 != id3
        assert id1.startswith("DI-")
        assert id2.startswith("DI-")

    def test_generate_check_id(self, checker: DataIntegrityChecker):
        """Test check ID generation."""
        check_id = checker._generate_check_id()

        assert check_id.startswith("CHK-")
        assert len(check_id) == 12  # "CHK-" + 8 char UUID

    @pytest.mark.asyncio
    async def test_validate_tenant_isolation_no_session(self, checker: DataIntegrityChecker):
        """Test tenant isolation validation without session."""
        result = await checker.validate_tenant_isolation(tenant_id=1)

        assert result.status == IntegrityStatus.SKIPPED
        assert len(result.issues_found) == 0

    @pytest.mark.asyncio
    async def test_validate_tenant_isolation_with_session(
        self, checker_with_session: DataIntegrityChecker, mock_session: AsyncMock
    ):
        """Test tenant isolation validation with session."""
        # Mock the session.execute to return tenant_id exists
        mock_result = MagicMock()
        mock_result.scalar.return_value = "tenant_id"
        mock_session.execute.return_value = mock_result

        result = await checker_with_session.validate_tenant_isolation(
            tenant_id=1, tables=["workflows"]
        )

        assert result.check_type == IntegrityCheckType.TENANT_ISOLATION
        assert "workflows" in result.tables_checked

    @pytest.mark.asyncio
    async def test_verify_foreign_keys_no_session(self, checker: DataIntegrityChecker):
        """Test FK verification without session."""
        result = await checker.verify_foreign_keys()

        assert result.status == IntegrityStatus.SKIPPED
        assert len(result.issues_found) == 0

    @pytest.mark.asyncio
    async def test_verify_foreign_keys_with_session(
        self, checker_with_session: DataIntegrityChecker, mock_session: AsyncMock
    ):
        """Test FK verification with session."""
        # Mock the session.execute to return no orphans
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_session.execute.return_value = mock_result

        result = await checker_with_session.verify_foreign_keys(tables=["workflows"])

        assert result.check_type == IntegrityCheckType.FOREIGN_KEY

    @pytest.mark.asyncio
    async def test_detect_duplicates_no_session(self, checker: DataIntegrityChecker):
        """Test duplicate detection without session."""
        result = await checker.detect_duplicates(
            table_name="workflows",
            unique_columns=["name"],
        )

        assert result.status == IntegrityStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_detect_duplicates_no_duplicates(
        self, checker_with_session: DataIntegrityChecker, mock_session: AsyncMock
    ):
        """Test duplicate detection when no duplicates exist."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        result = await checker_with_session.detect_duplicates(
            table_name="workflows",
            unique_columns=["name"],
        )

        assert result.status == IntegrityStatus.PASSED
        assert len(result.issues_found) == 0

    @pytest.mark.asyncio
    async def test_compute_data_checksum_no_session(self, checker: DataIntegrityChecker):
        """Test checksum computation without session."""
        result = await checker.compute_data_checksum("workflows")

        assert result["table_name"] == "workflows"
        assert result["checksum"] is None
        assert "error" in result

    @pytest.mark.asyncio
    async def test_compute_data_checksum_with_session(
        self, checker_with_session: DataIntegrityChecker, mock_session: AsyncMock
    ):
        """Test checksum computation with session."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 100  # row count
        mock_session.execute.return_value = mock_result

        result = await checker_with_session.compute_data_checksum(
            table_name="workflows",
            tenant_id=1,
        )

        assert result["table_name"] == "workflows"
        assert result["checksum"] is not None
        assert result["row_count"] == 100
        assert result["tenant_id"] == 1

    @pytest.mark.asyncio
    async def test_validate_not_null_constraints_no_session(self, checker: DataIntegrityChecker):
        """Test NOT NULL validation without session."""
        result = await checker.validate_not_null_constraints(
            table_name="workflows",
            required_columns=["name", "tenant_id"],
        )

        assert result.status == IntegrityStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_validate_not_null_constraints_with_nulls(
        self, checker_with_session: DataIntegrityChecker, mock_session: AsyncMock
    ):
        """Test NOT NULL validation when NULLs exist."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5  # 5 NULL values found
        mock_session.execute.return_value = mock_result

        result = await checker_with_session.validate_not_null_constraints(
            table_name="workflows",
            required_columns=["name"],
        )

        assert result.status == IntegrityStatus.FAILED
        assert len(result.issues_found) > 0
        assert result.issues_found[0].affected_rows == 5

    @pytest.mark.asyncio
    async def test_run_all_checks(
        self, checker_with_session: DataIntegrityChecker, mock_session: AsyncMock
    ):
        """Test running all integrity checks."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        results = await checker_with_session.run_all_checks(tenant_id=1)

        assert len(results) >= 1  # At least FK check runs

    def test_generate_report_text(self, checker: DataIntegrityChecker):
        """Test text report generation."""
        results = [
            IntegrityCheckResult(
                check_id="CHK-test1",
                check_type=IntegrityCheckType.TENANT_ISOLATION,
                status=IntegrityStatus.PASSED,
                tables_checked=["workflows", "tasks"],
                issues_found=[],
                duration_ms=50.5,
            )
        ]

        report = checker.generate_report(results, format="text")

        assert "DATA INTEGRITY CHECK REPORT" in report
        assert "CHK-test1" in report
        assert "[OK]" in report
        assert "workflows" in report

    def test_generate_report_json(self, checker: DataIntegrityChecker):
        """Test JSON report generation."""
        import json

        results = [
            IntegrityCheckResult(
                check_id="CHK-test1",
                check_type=IntegrityCheckType.FOREIGN_KEY,
                status=IntegrityStatus.PASSED,
                tables_checked=["workflows"],
                issues_found=[],
                duration_ms=25.0,
            )
        ]

        report = checker.generate_report(results, format="json")

        # Should be valid JSON
        parsed = json.loads(report)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["check_id"] == "CHK-test1"

    def test_generate_report_with_issues(self, checker: DataIntegrityChecker):
        """Test report generation with issues."""
        issue = IntegrityIssue(
            issue_id="DI-00001",
            check_type=IntegrityCheckType.ORPHAN_RECORD,
            status=IntegrityStatus.FAILED,
            table_name="tasks",
            column_name="workflow_id",
            description="Found 10 orphan records",
            affected_rows=10,
            severity="high",
            recommendation="Clean up orphan records",
        )

        results = [
            IntegrityCheckResult(
                check_id="CHK-test1",
                check_type=IntegrityCheckType.FOREIGN_KEY,
                status=IntegrityStatus.FAILED,
                tables_checked=["tasks"],
                issues_found=[issue],
                duration_ms=100.0,
            )
        ]

        report = checker.generate_report(results)

        assert "[FAIL]" in report
        assert "Found 10 orphan records" in report
        assert "[HIGH]" in report


class TestIntegrityCheckResult:
    """Test IntegrityCheckResult dataclass."""

    def test_is_clean_property_true(self):
        """Test is_clean property returns True when no issues."""
        result = IntegrityCheckResult(
            check_id="test",
            check_type=IntegrityCheckType.TENANT_ISOLATION,
            status=IntegrityStatus.PASSED,
            tables_checked=["workflows"],
            issues_found=[],
            duration_ms=50.0,
        )

        assert result.is_clean is True

    def test_is_clean_property_false(self):
        """Test is_clean property returns False when issues exist."""
        issue = IntegrityIssue(
            issue_id="DI-1",
            check_type=IntegrityCheckType.NULL_CHECK,
            status=IntegrityStatus.FAILED,
            table_name="test",
            column_name="col",
            description="Test issue",
            affected_rows=1,
            severity="high",
            recommendation="Fix it",
        )

        result = IntegrityCheckResult(
            check_id="test",
            check_type=IntegrityCheckType.NULL_CHECK,
            status=IntegrityStatus.FAILED,
            tables_checked=["test"],
            issues_found=[issue],
            duration_ms=50.0,
        )

        assert result.is_clean is False

    def test_critical_issues_property(self):
        """Test critical_issues property filters correctly."""
        issues = [
            IntegrityIssue(
                issue_id="DI-1",
                check_type=IntegrityCheckType.NULL_CHECK,
                status=IntegrityStatus.FAILED,
                table_name="test",
                column_name="col",
                description="Low issue",
                affected_rows=1,
                severity="low",
                recommendation="Fix",
            ),
            IntegrityIssue(
                issue_id="DI-2",
                check_type=IntegrityCheckType.TENANT_ISOLATION,
                status=IntegrityStatus.FAILED,
                table_name="test",
                column_name="tenant_id",
                description="Critical issue",
                affected_rows=100,
                severity="critical",
                recommendation="Fix now",
            ),
        ]

        result = IntegrityCheckResult(
            check_id="test",
            check_type=IntegrityCheckType.TENANT_ISOLATION,
            status=IntegrityStatus.FAILED,
            tables_checked=["test"],
            issues_found=issues,
            duration_ms=50.0,
        )

        critical = result.critical_issues

        assert len(critical) == 1
        assert critical[0].severity == "critical"

    def test_to_dict(self):
        """Test to_dict method."""
        result = IntegrityCheckResult(
            check_id="CHK-test",
            check_type=IntegrityCheckType.DUPLICATE,
            status=IntegrityStatus.WARNING,
            tables_checked=["workflows", "tasks"],
            issues_found=[],
            duration_ms=75.5,
        )

        data = result.to_dict()

        assert data["check_id"] == "CHK-test"
        assert data["check_type"] == "duplicate"
        assert data["status"] == "warning"
        assert data["tables_checked"] == ["workflows", "tasks"]
        assert data["issues_count"] == 0
        assert data["is_clean"] is True
        assert "timestamp" in data


class TestIntegrityIssue:
    """Test IntegrityIssue dataclass."""

    def test_to_dict(self):
        """Test to_dict method."""
        issue = IntegrityIssue(
            issue_id="DI-00001",
            check_type=IntegrityCheckType.ORPHAN_RECORD,
            status=IntegrityStatus.FAILED,
            table_name="tasks",
            column_name="workflow_id",
            description="Found orphan records",
            affected_rows=5,
            severity="high",
            recommendation="Delete or reassign",
            sample_data=[{"id": 1}, {"id": 2}],
        )

        data = issue.to_dict()

        assert data["issue_id"] == "DI-00001"
        assert data["check_type"] == "orphan_record"
        assert data["status"] == "failed"
        assert data["table_name"] == "tasks"
        assert data["column_name"] == "workflow_id"
        assert data["affected_rows"] == 5
        assert data["sample_data"] == [{"id": 1}, {"id": 2}]


class TestIntegrityEnums:
    """Test integrity-related enums."""

    def test_check_type_values(self):
        """Test IntegrityCheckType enum values."""
        assert IntegrityCheckType.CHECKSUM.value == "checksum"
        assert IntegrityCheckType.FOREIGN_KEY.value == "foreign_key"
        assert IntegrityCheckType.TENANT_ISOLATION.value == "tenant_isolation"
        assert IntegrityCheckType.CONSTRAINT.value == "constraint"
        assert IntegrityCheckType.ORPHAN_RECORD.value == "orphan_record"
        assert IntegrityCheckType.DUPLICATE.value == "duplicate"
        assert IntegrityCheckType.NULL_CHECK.value == "null_check"
        assert IntegrityCheckType.RANGE_CHECK.value == "range_check"

    def test_integrity_status_values(self):
        """Test IntegrityStatus enum values."""
        assert IntegrityStatus.PASSED.value == "passed"
        assert IntegrityStatus.FAILED.value == "failed"
        assert IntegrityStatus.WARNING.value == "warning"
        assert IntegrityStatus.SKIPPED.value == "skipped"


class TestFactoryFunction:
    """Test factory function."""

    def test_create_integrity_checker_without_session(self):
        """Test creating checker without session."""
        checker = create_integrity_checker()
        assert isinstance(checker, DataIntegrityChecker)
        assert checker.session is None

    def test_create_integrity_checker_with_session(self, mock_session: AsyncMock):
        """Test creating checker with session."""
        checker = create_integrity_checker(session=mock_session)
        assert isinstance(checker, DataIntegrityChecker)
        assert checker.session == mock_session


class TestTenantIsolatedTables:
    """Test tenant isolation constants."""

    def test_tenant_isolated_tables_defined(self):
        """Test that tenant isolated tables are defined."""
        assert len(DataIntegrityChecker.TENANT_ISOLATED_TABLES) > 0
        assert "workflows" in DataIntegrityChecker.TENANT_ISOLATED_TABLES
        assert "tasks" in DataIntegrityChecker.TENANT_ISOLATED_TABLES

    def test_system_tables_defined(self):
        """Test that system tables are defined."""
        assert len(DataIntegrityChecker.SYSTEM_TABLES) > 0
        assert "tenants" in DataIntegrityChecker.SYSTEM_TABLES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
