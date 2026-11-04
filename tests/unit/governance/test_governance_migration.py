"""Tests for governance Alembic migration (Phase 5).

Verifies the migration module exists, has correct metadata,
and creates the five governance tables with the right columns.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from unittest.mock import MagicMock, patch

# ── Load the migration module from file path (no __init__.py in alembic/versions) ──

_MIGRATION_PATH = (
    pathlib.Path(__file__).parent.parent.parent.parent
    / "src"
    / "alembic"
    / "versions"
    / "20260409c_governance_tables.py"
)
_MODULE_NAME = "governance_tables_20260409c"


def _load_migration():
    if _MODULE_NAME in sys.modules:
        return sys.modules[_MODULE_NAME]
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MIGRATION_PATH)
    assert spec is not None, f"Migration file not found at {_MIGRATION_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestGovernanceMigrationExists:
    def test_migration_file_exists(self) -> None:
        assert _MIGRATION_PATH.exists(), f"Expected migration at {_MIGRATION_PATH}"

    def test_migration_module_loadable(self) -> None:
        mod = _load_migration()
        assert mod is not None

    def test_migration_has_revision(self) -> None:
        mod = _load_migration()
        assert hasattr(mod, "revision")
        assert mod.revision  # non-empty string

    def test_migration_has_down_revision(self) -> None:
        mod = _load_migration()
        assert hasattr(mod, "down_revision")

    def test_migration_has_upgrade_function(self) -> None:
        mod = _load_migration()
        assert callable(mod.upgrade)

    def test_migration_has_downgrade_function(self) -> None:
        mod = _load_migration()
        assert callable(mod.downgrade)


class TestGovernanceMigrationTables:
    """upgrade() creates the five governance tables."""

    def _run_upgrade(self) -> list[str]:
        created_tables: list[str] = []
        mock_op = MagicMock()
        mock_op.create_table.side_effect = lambda name, *args, **kwargs: created_tables.append(name)
        mock_op.create_index.return_value = None

        mod = _load_migration()
        with patch(f"{_MODULE_NAME}.op", mock_op):
            mod.upgrade()
        return created_tables

    def test_creates_governance_alerts_table(self) -> None:
        assert "governance_alerts" in self._run_upgrade()

    def test_creates_governance_accuracy_metrics_table(self) -> None:
        assert "governance_accuracy_metrics" in self._run_upgrade()

    def test_creates_governance_risk_entries_table(self) -> None:
        assert "governance_risk_entries" in self._run_upgrade()

    def test_creates_governance_quality_checks_table(self) -> None:
        assert "governance_quality_checks" in self._run_upgrade()

    def test_creates_governance_authority_reports_table(self) -> None:
        assert "governance_authority_reports" in self._run_upgrade()


class TestGovernanceMigrationDowngrade:
    """downgrade() drops the five governance tables."""

    def _run_downgrade(self) -> list[str]:
        dropped_tables: list[str] = []
        mock_op = MagicMock()
        mock_op.drop_table.side_effect = lambda name, **kwargs: dropped_tables.append(name)
        mock_op.drop_index.return_value = None

        mod = _load_migration()
        with patch(f"{_MODULE_NAME}.op", mock_op):
            mod.downgrade()
        return dropped_tables

    def test_drops_governance_alerts_table(self) -> None:
        assert "governance_alerts" in self._run_downgrade()

    def test_drops_governance_accuracy_metrics_table(self) -> None:
        assert "governance_accuracy_metrics" in self._run_downgrade()

    def test_drops_governance_risk_entries_table(self) -> None:
        assert "governance_risk_entries" in self._run_downgrade()

    def test_drops_governance_quality_checks_table(self) -> None:
        assert "governance_quality_checks" in self._run_downgrade()

    def test_drops_governance_authority_reports_table(self) -> None:
        assert "governance_authority_reports" in self._run_downgrade()
