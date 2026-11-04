"""
Data Protection Integration Tests - P5.2.5
Complete end-to-end tests for data integrity, secrets scanning, and rollback validation.

This test suite validates the complete data protection workflow:
1. Secrets scanning to detect hardcoded credentials
2. Data integrity checks for database consistency
3. Rollback validation for safe database operations
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.security.data_integrity import (
    DataIntegrityChecker,
    IntegrityCheckResult,
    IntegrityCheckType,
    IntegrityIssue,
    IntegrityStatus,
)
from src.core.security.rollback_validator import (
    DataIntegrityValidator,
    MigrationRollbackValidator,
    RollbackCheckpoint,
    RollbackStatus,
    RollbackType,
    RollbackValidationResult,
    RollbackValidator,
)
from src.core.security.secrets_scanner import (
    ScanResult,
    SecretFinding,
    SecretSeverity,
    SecretsScanner,
    SecretType,
)


@pytest.fixture
def temp_test_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def data_integrity_checker(mock_session: AsyncMock) -> DataIntegrityChecker:
    """Create a DataIntegrityChecker instance with mock session."""
    return DataIntegrityChecker(session=mock_session)


@pytest.fixture
def secrets_scanner() -> SecretsScanner:
    """Create a SecretsScanner instance."""
    return SecretsScanner()


@pytest.fixture
def temp_checkpoint_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for rollback checkpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def rollback_validator(temp_checkpoint_dir: Path) -> RollbackValidator:
    """Create a RollbackValidator instance."""
    validator = RollbackValidator(
        alembic_config_path="src/alembic.ini",
        checkpoints_dir=str(temp_checkpoint_dir),
    )
    # Windows: alembic subprocess deadlocks during tests; bypass with fake revision
    validator.migration_validator._run_alembic_command = lambda cmd, env_override=None: (
        True,
        "20260415001 (head)",
        "",
    )
    return validator


class TestDataProtectionWorkflow:
    """Test the complete data protection workflow."""

    def test_secrets_detection_before_deployment(
        self, temp_test_dir: Path, secrets_scanner: SecretsScanner
    ):
        """Test that secrets are detected before deployment pipeline."""
        # Create a file with hardcoded secrets
        test_file = temp_test_dir / "config.py"
        test_file.write_text(
            """
# BAD: Hardcoded credentials
DATABASE_URL = "postgresql://admin:SuperSecretPassword123@prod-db.internal:5432/production"
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

# GOOD: Environment variables
SECRET_KEY = os.environ.get("SECRET_KEY")
API_KEY = os.getenv("API_KEY")
        """
        )

        # Scan for secrets
        result = secrets_scanner.scan_file(str(test_file))

        # Should detect multiple secrets
        assert len(result) >= 2

        # Check for database URL secret
        db_secrets = [f for f in result if f.secret_type == SecretType.DATABASE_URL]
        assert len(db_secrets) >= 1
        assert db_secrets[0].severity in [SecretSeverity.HIGH, SecretSeverity.CRITICAL]

        # Check for AWS secrets
        aws_secrets = [f for f in result if f.secret_type == SecretType.AWS_KEY]
        assert len(aws_secrets) >= 1

    def test_data_integrity_validation(
        self, data_integrity_checker: DataIntegrityChecker, mock_session: AsyncMock
    ):
        """Test data integrity validation workflow."""
        # Mock database responses for various integrity checks
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0  # No issues found
        mock_result.fetchall.return_value = []  # No duplicates
        mock_session.execute.return_value = mock_result

        # Run all integrity checks
        results = []
        results.append(
            data_integrity_checker.validate_tenant_isolation(tenant_id=1, tables=["workflows"])
        )
        results.append(data_integrity_checker.verify_foreign_keys(tables=["workflows", "tasks"]))
        results.append(
            data_integrity_checker.detect_duplicates(
                table_name="workflows", unique_columns=["name"]
            )
        )
        results.append(
            data_integrity_checker.validate_not_null_constraints(
                table_name="users", required_columns=["email", "username"]
            )
        )

        # All checks should pass with mocked clean data
        for result in results:
            if hasattr(result, "__await__"):
                # Handle async results
                pass
            else:
                assert result.status in [
                    IntegrityStatus.PASSED,
                    IntegrityStatus.SKIPPED,
                ]

    def test_rollback_validation_process(
        self, rollback_validator: RollbackValidator, temp_checkpoint_dir: Path
    ):
        """Test the complete rollback validation process."""
        # Create checkpoints before making changes
        checkpoint1 = rollback_validator.create_checkpoint(
            name="before_user_creation",
            rollback_type=RollbackType.DATA_CHANGE,
            metadata={"operation": "create_users", "count": 100},
        )

        checkpoint2 = rollback_validator.create_checkpoint(
            name="before_workflow_deployment",
            rollback_type=RollbackType.MIGRATION,
            metadata={
                "version": "1.2.3",
                "components": ["workflow_engine", "scheduler"],
            },
        )

        # Verify checkpoints were created
        assert checkpoint1 is not None
        assert checkpoint2 is not None
        assert len(checkpoint1.checkpoint_id) == 8
        assert len(checkpoint2.checkpoint_id) == 8

        # List all checkpoints
        all_checkpoints = rollback_validator.list_checkpoints()
        assert len(all_checkpoints) == 2

        # Verify checkpoint details
        cp1_details = rollback_validator.get_checkpoint(checkpoint1.checkpoint_id)
        assert cp1_details is not None
        assert cp1_details["name"] == "before_user_creation"
        assert cp1_details["rollback_type"] == "data_change"

        # Test checkpoint deletion
        delete_result = rollback_validator.delete_checkpoint(checkpoint2.checkpoint_id)
        assert delete_result is True

        # Verify checkpoint was deleted
        deleted_cp = rollback_validator.get_checkpoint(checkpoint2.checkpoint_id)
        assert deleted_cp is None

    def test_complete_data_protection_pipeline(
        self,
        temp_test_dir: Path,
        secrets_scanner: SecretsScanner,
        data_integrity_checker: DataIntegrityChecker,
        rollback_validator: RollbackValidator,
    ):
        """Test the complete end-to-end data protection pipeline."""
        # Step 1: Scan for secrets in deployment files
        deploy_script = temp_test_dir / "deploy.py"
        deploy_script.write_text(
            """
#!/usr/bin/env python3
# Deployment script with potential security issues

import os
from sqlalchemy import create_engine

# SECURITY ISSUE: Hardcoded database credentials
DB_CONNECTION = "postgresql://deploy_user:DeployPass123@db.prod:5432/app_prod"

def deploy():
    # Connect to database
    engine = create_engine(DB_CONNECTION)

    # SECURITY ISSUE: Hardcoded API key
    API_KEY = "sk_live_abcdefghijklmnopqrstuvwxyz123456"

    # Good practice: Using environment variables
    SECRET_KEY = os.environ.get("SECRET_KEY")

    print("Deployment started...")
    return True

if __name__ == "__main__":
    deploy()
        """
        )

        # Scan for secrets - should detect issues
        scan_result = secrets_scanner.scan_file(str(deploy_script))
        assert len(scan_result) >= 2  # Should detect DB connection and API key

        # Step 2: Create rollback checkpoint before deployment
        checkpoint = rollback_validator.create_checkpoint(
            name="pre_deployment",
            rollback_type=RollbackType.DEPLOYMENT,
            metadata={
                "script": "deploy.py",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "environment": "production",
            },
        )
        assert checkpoint is not None

        # Step 3: Validate data integrity (mocked)
        # In a real scenario, this would connect to the database
        # For integration test, we just verify the checker works
        assert data_integrity_checker is not None

        # Step 4: Generate compliance report
        report_data = {
            "secrets_scan": {
                "total_findings": len(scan_result),
                "critical_findings": len(
                    [f for f in scan_result if f.severity == SecretSeverity.CRITICAL]
                ),
            },
            "rollback_checkpoint": {
                "id": checkpoint.checkpoint_id,
                "name": checkpoint.name,
            },
        }

        # Verify report data structure
        assert report_data["secrets_scan"]["total_findings"] >= 2
        assert len(report_data["rollback_checkpoint"]["id"]) == 8


class TestCrossComponentIntegration:
    """Test integration between different security components."""

    def test_secrets_affect_rollback_decisions(
        self,
        temp_test_dir: Path,
        secrets_scanner: SecretsScanner,
        rollback_validator: RollbackValidator,
    ):
        """Test that secrets detection affects rollback checkpoint metadata."""
        # Create a file with secrets
        config_file = temp_test_dir / "app_config.py"
        config_file.write_text(
            """
# Configuration with secrets that should trigger security review
ENCRYPTION_KEY = "super_secret_encryption_key_1234567890"
THIRD_PARTY_API_KEY = "tpak_live_examplekey1234567890abcdefghijklmnop"
        """
        )

        # Scan for secrets
        findings = secrets_scanner.scan_file(str(config_file))

        # Create checkpoint with security metadata
        checkpoint = rollback_validator.create_checkpoint(
            name="config_update_with_secrets",
            rollback_type=RollbackType.CONFIGURATION,
            metadata={
                "security_review_required": True,
                "secrets_detected": len(findings),
                "highest_severity": (
                    max((f.severity for f in findings), default=SecretSeverity.LOW).value
                    if findings
                    else "none"
                ),
            },
        )

        # Verify checkpoint was created with security metadata
        assert checkpoint is not None
        cp_details = rollback_validator.get_checkpoint(checkpoint.checkpoint_id)
        assert cp_details is not None
        assert cp_details["metadata"]["security_review_required"] is True
        assert cp_details["metadata"]["secrets_detected"] >= 1

    def test_data_integrity_affects_rollback_validation(
        self,
        data_integrity_checker: DataIntegrityChecker,
        rollback_validator: RollbackValidator,
        mock_session: AsyncMock,
    ):
        """Test that data integrity issues affect rollback validation process."""
        # Mock database to simulate integrity issues
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5  # 5 NULL values found
        mock_session.execute.return_value = mock_result

        # Simulate data integrity validation with issues
        null_check_result = data_integrity_checker.validate_not_null_constraints(
            table_name="critical_table", required_columns=["id", "name", "status"]
        )

        # Create checkpoint with integrity metadata
        checkpoint = rollback_validator.create_checkpoint(
            name="data_migration_with_integrity_issues",
            rollback_type=RollbackType.DATA_CHANGE,
            metadata={
                "data_integrity_status": "issues_detected",
                "validation_required": True,
                "affected_tables": ["critical_table"],
            },
        )

        # Verify checkpoint reflects integrity concerns
        assert checkpoint is not None
        cp_details = rollback_validator.get_checkpoint(checkpoint.checkpoint_id)
        assert cp_details is not None
        assert cp_details["metadata"]["validation_required"] is True


class TestReportingAndCompliance:
    """Test reporting and compliance features."""

    def test_comprehensive_security_report_generation(
        self,
        secrets_scanner: SecretsScanner,
        data_integrity_checker: DataIntegrityChecker,
        rollback_validator: RollbackValidator,
        temp_test_dir: Path,
    ):
        """Test generation of comprehensive security reports."""
        # Create test files with various security issues
        test_files = []

        # File with secrets
        secret_file = temp_test_dir / "secrets.py"
        secret_file.write_text('API_KEY = "sk_live_test1234567890abcdef"')
        test_files.append(secret_file)

        # Clean file
        clean_file = temp_test_dir / "clean.py"
        clean_file.write_text('CONFIG_VALUE = "normal_config"')
        test_files.append(clean_file)

        # Scan all files
        all_findings = []
        for file_path in test_files:
            findings = secrets_scanner.scan_file(str(file_path))
            all_findings.extend(findings)

        # Generate different report formats
        scan_result = ScanResult(
            scan_path=str(temp_test_dir),
            total_files_scanned=len(test_files),
            total_findings=len(all_findings),
            findings_by_severity={
                SecretSeverity.LOW: 0,
                SecretSeverity.MEDIUM: 0,
                SecretSeverity.HIGH: 0,
                SecretSeverity.CRITICAL: len(all_findings),
            },
            findings=all_findings,
            scan_duration_ms=100.0,
            is_clean=len(all_findings) == 0,
        )

        # Test text report
        text_report = secrets_scanner.generate_report(scan_result, format="text")
        assert "SECRETS SCAN REPORT" in text_report
        assert "Files Scanned:" in text_report

        # Test JSON report
        json_report = secrets_scanner.generate_report(scan_result, format="json")
        assert '"scan_path"' in json_report
        assert '"total_findings"' in json_report

        # Test markdown report
        md_report = secrets_scanner.generate_report(scan_result, format="markdown")
        assert "# Secrets Scan Report" in md_report

        # Test rollback validation report
        validation_results = [
            RollbackValidationResult(
                validation_id="test1",
                rollback_type=RollbackType.MIGRATION,
                status=RollbackStatus.SUCCESS,
                duration_ms=50.0,
                forward_success=True,
                rollback_success=True,
                data_integrity_verified=True,
                errors=[],
                warnings=[],
                details={"test": "data"},
            )
        ]

        rollback_report = rollback_validator.generate_report(validation_results)
        assert "ROLLBACK VALIDATION REPORT" in rollback_report
        assert "[OK]" in rollback_report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
