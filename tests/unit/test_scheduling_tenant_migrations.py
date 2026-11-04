"""TDD checks for scheduling tenant migration chain.

These tests enforce an explicit expand -> backfill -> contract sequence.
"""

import importlib.util
from pathlib import Path

import pytest

_BACKFILL_PATH = Path("src/alembic/versions/20260409a_sched_tenant_backfill.py")
_CONTRACT_PATH = Path("src/alembic/versions/20260409b_add_fk_constraints_scheduling.py")
_MODULE_NAME = "sched_tenant_backfill_20260409a"


def _load_backfill_module():
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _BACKFILL_PATH)
    assert spec is not None, f"Migration file not found at {_BACKFILL_PATH}"
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_backfill_migration_exists() -> None:
    """Backfill migration must exist between add-column and FK contract migrations."""
    assert _BACKFILL_PATH.exists(), f"Expected migration at {_BACKFILL_PATH}"


def test_backfill_migration_metadata() -> None:
    """Backfill migration must chain from expand migration."""
    mod = _load_backfill_module()
    assert mod.revision == "20260409a_sched_tenant_backfill"
    assert mod.down_revision == "20260409_sched_tenant"


def test_contract_migration_depends_on_backfill() -> None:
    """Contract migration must run only after backfill migration."""
    content = _CONTRACT_PATH.read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260409a_sched_tenant_backfill"' in content


def test_backfill_updates_both_scheduling_tables() -> None:
    """Backfill migration must update webhook registrations and sync conflicts."""
    content = _BACKFILL_PATH.read_text(encoding="utf-8")
    assert "UPDATE scheduling_webhook_registrations" in content
    assert "UPDATE scheduling_sync_conflicts" in content
    assert "scheduling_calendar_integrations" in content
    assert "tenant_id IS NULL" in content


def test_backfill_raises_on_orphan_webhook_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backfill must hard-fail when orphan rows leave tenant_id unresolved."""
    mod = _load_backfill_module()

    class _FakeResult:
        def __init__(self, value: int):
            self._value = value

        def scalar(self) -> int:
            return self._value

    class _FakeConnection:
        def execute(self, stmt):
            sql = str(stmt)
            if "SELECT COUNT(*) FROM scheduling_webhook_registrations" in sql:
                # Simulate unresolved orphan row: no matching integration_id.
                return _FakeResult(1)
            return _FakeResult(0)

    class _FakeInspector:
        def has_table(self, table_name: str) -> bool:
            return table_name in {
                "scheduling_calendar_integrations",
                "scheduling_webhook_registrations",
            }

        def get_columns(self, table_name: str):
            if table_name == "scheduling_calendar_integrations":
                return [{"name": "tenant_id"}]
            if table_name == "scheduling_webhook_registrations":
                return [{"name": "tenant_id"}, {"name": "integration_id"}]
            return []

    fake_connection = _FakeConnection()
    monkeypatch.setattr(mod.op, "get_bind", lambda: fake_connection)
    monkeypatch.setattr(mod.sa, "inspect", lambda _: _FakeInspector())

    with pytest.raises(RuntimeError, match="scheduling_webhook_registrations"):
        mod.upgrade()
