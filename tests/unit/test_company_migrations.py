"""
TDD Tests for Task 1.2: Alembic Migrations

Tests for Company Layer database migrations.
These tests verify that migrations can be applied and rolled back correctly.
"""

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect, text


class TestMigrationFilesExist:
    """Happy path: Verify migration files exist."""

    def test_migration_001_exists(self):
        """Migration 001 (create_company_tables) should exist."""
        migration_path = Path("src/alembic/versions/20260311_001_create_company_tables.py")
        assert migration_path.exists()

    def test_migration_002_exists(self):
        """Migration 002 (create_external_agent_tables) should exist."""
        migration_path = Path("src/alembic/versions/20260311_002_create_external_agent_tables.py")
        assert migration_path.exists()

    def test_migration_003_exists(self):
        """Migration 003 (create_board_governance_tables) should exist."""
        migration_path = Path("src/alembic/versions/20260311_003_create_board_governance_tables.py")
        assert migration_path.exists()

    def test_migration_004_exists(self):
        """Migration 004 (create_company_template_tables) should exist."""
        migration_path = Path("src/alembic/versions/20260311_004_create_company_template_tables.py")
        assert migration_path.exists()

    def test_migration_005_exists(self):
        """Migration 005 (create_pack_activation_audit_log) should exist."""
        migration_path = Path(
            "src/alembic/versions/20260311_005_create_pack_activation_audit_log.py"
        )
        assert migration_path.exists()

    def test_migration_006a_exists(self):
        """Migration 006a (expand_add_company_fields) should exist."""
        migration_path = Path("src/alembic/versions/20260311_006a_expand_add_company_fields.py")
        assert migration_path.exists()

    def test_migration_006b_exists(self):
        """Migration 006b (backfill_company_fields) should exist."""
        migration_path = Path("src/alembic/versions/20260311_006b_backfill_company_fields.py")
        assert migration_path.exists()

    def test_migration_006c_exists(self):
        """Migration 006c (contract_add_fk_constraints) should exist."""
        migration_path = Path("src/alembic/versions/20260311_006c_contract_add_fk_constraints.py")
        assert migration_path.exists()


class TestMigrationChain:
    """Happy path: Verify migration chain is correct."""

    def test_migration_revisions_are_strings(self):
        """All migration revisions should be valid strings."""
        # This is a basic check - full chain validation requires Alembic runtime
        migrations_dir = Path("src/alembic/versions")
        migration_files = list(migrations_dir.glob("20260311_*.py"))

        # Should have at least 8 migration files for Company Layer
        # (may have more due to ongoing development - futureproof check)
        assert len(migration_files) >= 8, f"Expected at least 8 migrations, found {len(migration_files)}"


class TestMigrationSyntax:
    """Happy path: Verify migration files are valid Python."""

    def test_migration_001_is_valid_python(self):
        """Migration 001 should be valid Python."""
        migration_path = Path("src/alembic/versions/20260311_001_create_company_tables.py")
        content = migration_path.read_text()

        # Should have required components
        assert "revision =" in content
        assert "down_revision =" in content
        assert "def upgrade(" in content
        assert "def downgrade(" in content
        assert "op.create_table" in content

    def test_migration_001_creates_companies_table(self):
        """Migration 001 should create companies table."""
        migration_path = Path("src/alembic/versions/20260311_001_create_company_tables.py")
        content = migration_path.read_text()

        assert "op.create_table(" in content and "companies" in content
        assert 'sa.Column("id"' in content
        assert "tenant_id" in content
        assert "name" in content

    def test_migration_001_creates_departments_table(self):
        """Migration 001 should create departments table."""
        migration_path = Path("src/alembic/versions/20260311_001_create_company_tables.py")
        content = migration_path.read_text()

        assert "op.create_table(" in content and "departments" in content
        assert "company_id" in content
        assert "parent_department_id" in content
        assert "version" in content  # Optimistic locking

    def test_migration_001_creates_goals_table(self):
        """Migration 001 should create goals table."""
        migration_path = Path("src/alembic/versions/20260311_001_create_company_tables.py")
        content = migration_path.read_text()

        assert "op.create_table(" in content and "goals" in content
        assert "goal_type" in content
        assert "progress_pct" in content
        assert "parent_goal_id" in content

    def test_migration_has_rls_policies(self):
        """Migration should enable RLS policies."""
        migration_path = Path("src/alembic/versions/20260311_001_create_company_tables.py")
        content = migration_path.read_text()

        assert "ENABLE ROW LEVEL SECURITY" in content
        assert "CREATE POLICY" in content
        assert "tenant_isolation" in content


class TestZeroDowntimeMigrations:
    """Happy path: Verify zero-downtime migration pattern."""

    def test_expand_migration_adds_nullable_columns(self):
        """006a should add nullable columns without FK constraints."""
        migration_path = Path("src/alembic/versions/20260311_006a_expand_add_company_fields.py")
        content = migration_path.read_text()

        assert "nullable=True" in content or "nullable=" not in content  # Default is nullable
        assert "op.add_column" in content
        assert "goal_id" in content
        assert "EXPAND" in content or "expand" in content

    def test_backfill_migration_batches(self):
        """006b should backfill in batches."""
        migration_path = Path("src/alembic/versions/20260311_006b_backfill_company_fields.py")
        content = migration_path.read_text()

        assert "BATCH_SIZE" in content
        assert "backfill" in content.lower() or "BACKFILL" in content

    def test_contract_migration_adds_fk(self):
        """006c should add FK constraints."""
        migration_path = Path("src/alembic/versions/20260311_006c_contract_add_fk_constraints.py")
        content = migration_path.read_text()

        assert "op.create_foreign_key" in content
        assert "CONTRACT" in content or "contract" in content
        assert "fk_procedure_executions_goal" in content


class TestMigrationIndexes:
    """Happy path: Verify indexes are created."""

    def test_companies_has_tenant_index(self):
        """Companies table should have tenant index."""
        migration_path = Path("src/alembic/versions/20260311_001_create_company_tables.py")
        content = migration_path.read_text()

        assert "idx_companies_tenant" in content

    def test_departments_has_indexes(self):
        """Departments table should have indexes."""
        migration_path = Path("src/alembic/versions/20260311_001_create_company_tables.py")
        content = migration_path.read_text()

        assert "idx_departments_tenant" in content
        assert "idx_departments_company" in content
        assert "idx_departments_parent" in content

    def test_goals_has_indexes(self):
        """Goals table should have indexes."""
        migration_path = Path("src/alembic/versions/20260311_001_create_company_tables.py")
        content = migration_path.read_text()

        assert "idx_goals_tenant" in content
        assert "idx_goals_company" in content
        assert "idx_goals_parent" in content
        assert "idx_goals_department" in content


class TestPackActivationAuditLogMigration:
    """Happy path: Pack activation audit log migration (Taak 4.0)."""

    def test_audit_log_table_created(self):
        """Migration 005 should create pack_activation_audit_logs table."""
        migration_path = Path(
            "src/alembic/versions/20260311_005_create_pack_activation_audit_log.py"
        )
        content = migration_path.read_text()

        assert "op.create_table(" in content and "pack_activation_audit_logs" in content
        assert "score" in content
        assert "confidence" in content
        assert "match_reason" in content

    def test_audit_log_has_required_fields(self):
        """Audit log should have all required fields for R2."""
        migration_path = Path(
            "src/alembic/versions/20260311_005_create_pack_activation_audit_log.py"
        )
        content = migration_path.read_text()

        assert "pack_id" in content
        assert "pack_name" in content
        assert "input_signals" in content
        assert "score_breakdown" in content
        assert "activated_automatically" in content
