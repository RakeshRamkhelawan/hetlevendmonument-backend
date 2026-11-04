"""
Unit tests for P5.1.8 - Data Integrity (A08): Rollback Validation

Tests the rollback validation functionality for database migrations,
deployments, and data changes.
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.security.rollback_validator import (
    DataIntegrityValidator,
    MigrationRollbackValidator,
    RollbackCheckpoint,
    RollbackStatus,
    RollbackType,
    RollbackValidationResult,
    RollbackValidator,
    create_validator,
)


@pytest.fixture
def temp_checkpoint_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for checkpoints."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def validator(temp_checkpoint_dir: Path) -> RollbackValidator:
    """Create a RollbackValidator instance for testing."""
    return RollbackValidator(
        alembic_config_path="src/alembic.ini",
        checkpoints_dir=str(temp_checkpoint_dir),
    )


@pytest.fixture
def validator_mocked_alembic(temp_checkpoint_dir: Path) -> Generator[RollbackValidator, None, None]:
    """Create a RollbackValidator with mocked alembic calls to prevent subprocess hangs."""
    with patch.object(
        RollbackValidator, '_capture_state', return_value={"revision": "abc123", "timestamp": "2024-01-01T00:00:00Z"}
    ):
        validator = RollbackValidator(
            alembic_config_path="src/alembic.ini",
            checkpoints_dir=str(temp_checkpoint_dir),
        )
        yield validator


@pytest.fixture
def migration_validator() -> MigrationRollbackValidator:
    """Create a MigrationRollbackValidator instance for testing."""
    return MigrationRollbackValidator(
        alembic_config_path="src/alembic.ini",
        test_database_url="sqlite:///./test_rollback.db",
    )


class TestRollbackValidator:
    """Test suite for RollbackValidator class."""

    def test_validator_initialization(self, validator: RollbackValidator):
        """Test that validator initializes correctly."""
        assert validator is not None
        assert validator.migration_validator is not None
        assert validator.integrity_validator is not None

    def test_create_checkpoint(self, validator_mocked_alembic: RollbackValidator, temp_checkpoint_dir: Path):
        """Test checkpoint creation."""
        checkpoint = validator_mocked_alembic.create_checkpoint(
            name="test_checkpoint",
            rollback_type=RollbackType.DATA_CHANGE,
            metadata={"test": "value"},
        )

        assert checkpoint is not None
        assert checkpoint.name == "test_checkpoint"
        assert checkpoint.rollback_type == RollbackType.DATA_CHANGE
        assert checkpoint.metadata == {"test": "value"}
        assert checkpoint.checkpoint_id is not None
        assert len(checkpoint.checkpoint_id) == 8

    def test_list_checkpoints(self, validator_mocked_alembic: RollbackValidator, temp_checkpoint_dir: Path):
        """Test listing checkpoints."""
        # Create some checkpoints
        validator_mocked_alembic.create_checkpoint("checkpoint1")
        validator_mocked_alembic.create_checkpoint("checkpoint2")
        validator_mocked_alembic.create_checkpoint("checkpoint3")

        checkpoints = validator_mocked_alembic.list_checkpoints()

        assert len(checkpoints) == 3
        assert any(cp["name"] == "checkpoint1" for cp in checkpoints)
        assert any(cp["name"] == "checkpoint2" for cp in checkpoints)
        assert any(cp["name"] == "checkpoint3" for cp in checkpoints)

    def test_get_checkpoint(self, validator_mocked_alembic: RollbackValidator, temp_checkpoint_dir: Path):
        """Test retrieving a specific checkpoint."""
        checkpoint = validator_mocked_alembic.create_checkpoint("test_get_checkpoint")

        retrieved = validator_mocked_alembic.get_checkpoint(checkpoint.checkpoint_id)

        assert retrieved is not None
        assert retrieved["name"] == "test_get_checkpoint"
        assert retrieved["checkpoint_id"] == checkpoint.checkpoint_id

    def test_get_checkpoint_not_found(self, validator_mocked_alembic: RollbackValidator):
        """Test retrieving a non-existent checkpoint."""
        retrieved = validator_mocked_alembic.get_checkpoint("nonexistent")

        assert retrieved is None

    def test_delete_checkpoint(self, validator_mocked_alembic: RollbackValidator, temp_checkpoint_dir: Path):
        """Test deleting a checkpoint."""
        checkpoint = validator_mocked_alembic.create_checkpoint("to_delete")

        # Verify checkpoint exists
        assert validator_mocked_alembic.get_checkpoint(checkpoint.checkpoint_id) is not None

        # Delete it
        result = validator_mocked_alembic.delete_checkpoint(checkpoint.checkpoint_id)

        assert result is True
        assert validator_mocked_alembic.get_checkpoint(checkpoint.checkpoint_id) is None

    def test_delete_checkpoint_not_found(self, validator: RollbackValidator):
        """Test deleting a non-existent checkpoint."""
        result = validator.delete_checkpoint("nonexistent")
        assert result is False

    def test_generate_report_text(self, validator: RollbackValidator):
        """Test text report generation."""
        results = [
            RollbackValidationResult(
                validation_id="test1",
                rollback_type=RollbackType.MIGRATION,
                status=RollbackStatus.SUCCESS,
                duration_ms=100.5,
                forward_success=True,
                rollback_success=True,
                data_integrity_verified=True,
                errors=[],
                warnings=[],
                details={},
            )
        ]

        report = validator.generate_report(results, format="text")

        assert "ROLLBACK VALIDATION REPORT" in report
        assert "test1" in report
        assert "[OK]" in report

    def test_generate_report_with_failures(self, validator: RollbackValidator):
        """Test report generation with failures."""
        results = [
            RollbackValidationResult(
                validation_id="fail1",
                rollback_type=RollbackType.MIGRATION,
                status=RollbackStatus.FAILED,
                duration_ms=50.0,
                forward_success=True,
                rollback_success=False,
                data_integrity_verified=False,
                errors=["Rollback failed: syntax error"],
                warnings=["Data may be inconsistent"],
                details={},
            )
        ]

        report = validator.generate_report(results)

        assert "[FAIL]" in report
        assert "Rollback failed: syntax error" in report
        assert "Data may be inconsistent" in report


class TestMigrationRollbackValidator:
    """Test suite for MigrationRollbackValidator class."""

    def test_migration_validator_initialization(
        self, migration_validator: MigrationRollbackValidator
    ):
        """Test migration validator initialization."""
        assert migration_validator is not None
        assert migration_validator.alembic_config_path == "src/alembic.ini"
        assert "sqlite" in migration_validator.test_database_url

    @patch("subprocess.run")
    def test_get_current_revision(
        self, mock_run: MagicMock, migration_validator: MigrationRollbackValidator
    ):
        """Test getting current migration revision."""
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123 (head)", stderr="")

        revision = migration_validator.get_current_revision()

        assert revision == "abc123"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_get_current_revision_empty(
        self, mock_run: MagicMock, migration_validator: MigrationRollbackValidator
    ):
        """Test getting revision when database has no migrations."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        revision = migration_validator.get_current_revision()

        assert revision is None

    @patch("subprocess.run")
    def test_get_revision_history(
        self, mock_run: MagicMock, migration_validator: MigrationRollbackValidator
    ):
        """Test getting migration revision history."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="rev1 -> rev2 (head), description\nbase -> rev1, initial",
            stderr="",
        )

        revisions = migration_validator.get_revision_history()

        assert len(revisions) >= 1

    @pytest.mark.asyncio
    @patch("subprocess.run")
    async def test_validate_migration_rollback_success(
        self, mock_run: MagicMock, migration_validator: MigrationRollbackValidator
    ):
        """Test successful migration rollback validation."""
        # All alembic commands succeed
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123 (head)", stderr="")

        result = await migration_validator.validate_migration_rollback(steps=1)

        # Check the result has expected structure
        assert result.rollback_type == RollbackType.MIGRATION
        assert result.validation_id is not None
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    @patch("subprocess.run")
    async def test_validate_migration_rollback_failure(
        self, mock_run: MagicMock, migration_validator: MigrationRollbackValidator
    ):
        """Test failed migration rollback validation."""
        # First call (upgrade) succeeds, second (downgrade) fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="OK", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="Error: syntax error"),
            MagicMock(returncode=0, stdout="OK", stderr=""),  # re-upgrade
        ]

        result = await migration_validator.validate_migration_rollback(steps=1)

        # Verify we got a result with the failure recorded
        assert result.rollback_type == RollbackType.MIGRATION
        # The rollback should have failed
        assert result.rollback_success is False or len(result.errors) > 0


class TestRollbackValidationResult:
    """Test suite for RollbackValidationResult dataclass."""

    def test_result_to_dict(self):
        """Test RollbackValidationResult.to_dict() method."""
        result = RollbackValidationResult(
            validation_id="test123",
            rollback_type=RollbackType.MIGRATION,
            status=RollbackStatus.SUCCESS,
            duration_ms=150.5,
            forward_success=True,
            rollback_success=True,
            data_integrity_verified=True,
            errors=[],
            warnings=["Minor warning"],
            details={"key": "value"},
        )

        data = result.to_dict()

        assert data["validation_id"] == "test123"
        assert data["rollback_type"] == "migration"
        assert data["status"] == "success"
        assert data["duration_ms"] == 150.5
        assert data["forward_success"] is True
        assert data["warnings"] == ["Minor warning"]
        assert "timestamp" in data


class TestRollbackCheckpoint:
    """Test suite for RollbackCheckpoint dataclass."""

    def test_checkpoint_to_dict(self):
        """Test RollbackCheckpoint.to_dict() method."""
        checkpoint = RollbackCheckpoint(
            checkpoint_id="cp123",
            name="test_checkpoint",
            rollback_type=RollbackType.DATA_CHANGE,
            created_at=datetime.now(timezone.utc),
            metadata={"key": "value"},
            hash_before="abc123",
            state_snapshot={"revision": "rev1"},
        )

        data = checkpoint.to_dict()

        assert data["checkpoint_id"] == "cp123"
        assert data["name"] == "test_checkpoint"
        assert data["rollback_type"] == "data_change"
        assert data["hash_before"] == "abc123"
        assert "created_at" in data


class TestDataIntegrityValidator:
    """Test suite for DataIntegrityValidator class."""

    def test_integrity_validator_initialization(self):
        """Test DataIntegrityValidator initialization."""
        validator = DataIntegrityValidator()
        assert validator is not None

    def test_compute_table_checksum(self):
        """Test table checksum computation."""
        validator = DataIntegrityValidator()

        checksum = validator.compute_table_checksum("test_table", ["col1", "col2"])

        assert checksum is not None
        assert len(checksum) == 32  # MD5 hash length

    def test_create_integrity_snapshot(self):
        """Test creating integrity snapshot."""
        validator = DataIntegrityValidator()
        validator._checksums = {"table1": "abc", "table2": "def"}

        snapshot = validator.create_integrity_snapshot("test_snapshot")

        assert snapshot["name"] == "test_snapshot"
        assert "created_at" in snapshot
        assert snapshot["checksums"] == {"table1": "abc", "table2": "def"}

    def test_compare_snapshots_no_changes(self):
        """Test comparing identical snapshots."""
        validator = DataIntegrityValidator()

        snapshot1 = {"checksums": {"table1": "abc", "table2": "def"}}
        snapshot2 = {"checksums": {"table1": "abc", "table2": "def"}}

        diff = validator.compare_snapshots(snapshot1, snapshot2)

        assert diff["tables_added"] == []
        assert diff["tables_removed"] == []
        assert diff["tables_modified"] == []

    def test_compare_snapshots_with_changes(self):
        """Test comparing snapshots with differences."""
        validator = DataIntegrityValidator()

        snapshot1 = {"checksums": {"table1": "abc", "table2": "def"}}
        snapshot2 = {"checksums": {"table1": "abc", "table2": "xyz", "table3": "new"}}

        diff = validator.compare_snapshots(snapshot1, snapshot2)

        assert "table3" in diff["tables_added"]
        assert "table2" in diff["tables_modified"]

    def test_compare_snapshots_with_removals(self):
        """Test comparing snapshots with removed tables."""
        validator = DataIntegrityValidator()

        snapshot1 = {"checksums": {"table1": "abc", "table2": "def", "table3": "ghi"}}
        snapshot2 = {"checksums": {"table1": "abc"}}

        diff = validator.compare_snapshots(snapshot1, snapshot2)

        assert "table2" in diff["tables_removed"]
        assert "table3" in diff["tables_removed"]


class TestFactoryFunctions:
    """Test factory functions."""

    def test_create_validator(self, temp_checkpoint_dir: Path):
        """Test create_validator factory function."""
        validator = create_validator(
            alembic_config_path="src/alembic.ini",
            checkpoints_dir=str(temp_checkpoint_dir),
        )

        assert isinstance(validator, RollbackValidator)


class TestRollbackStatusEnum:
    """Test RollbackStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert RollbackStatus.SUCCESS.value == "success"
        assert RollbackStatus.FAILED.value == "failed"
        assert RollbackStatus.PARTIAL.value == "partial"
        assert RollbackStatus.SKIPPED.value == "skipped"
        assert RollbackStatus.NOT_APPLICABLE.value == "not_applicable"


class TestRollbackTypeEnum:
    """Test RollbackType enum."""

    def test_type_values(self):
        """Test all type values exist."""
        assert RollbackType.MIGRATION.value == "migration"
        assert RollbackType.DEPLOYMENT.value == "deployment"
        assert RollbackType.DATA_CHANGE.value == "data_change"
        assert RollbackType.CONFIGURATION.value == "configuration"
        assert RollbackType.SCHEMA.value == "schema"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
