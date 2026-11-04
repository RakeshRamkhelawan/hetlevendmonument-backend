"""Regression tests for stale task index migration offline mode."""

import importlib.util
import sys
import types
from pathlib import Path


_MIGRATION_PATH = Path("src/alembic/versions/20260522b_stale_task_index.py")
_MODULE_NAME = "stale_task_index_migration_20260522b"


def _load_module():
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = types.SimpleNamespace(create_table=None, get_bind=None)
    fake_alembic.context = types.SimpleNamespace(is_offline_mode=lambda: False)
    sys.modules["alembic"] = fake_alembic

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MIGRATION_PATH)
    assert spec is not None, f"Migration file not found at {_MIGRATION_PATH}"
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_upgrade_offline_skips_inspection_and_creates_tables(monkeypatch) -> None:
    """Offline upgrade must not inspect MockConnection-backed binds."""
    mod = _load_module()
    created_tables: list[str] = []
    executed_sql: list[str] = []

    class _FakeConnection:
        def execute(self, statement):
            executed_sql.append(str(statement))
            return None

    monkeypatch.setattr(mod.op, "get_bind", lambda: _FakeConnection(), raising=False)
    monkeypatch.setattr(mod, "_is_offline", lambda _: True)
    monkeypatch.setattr(
        mod.sa,
        "inspect",
        lambda *_: (_ for _ in ()).throw(AssertionError("inspect should not run offline")),
    )
    monkeypatch.setattr(
        mod.op,
        "create_table",
        lambda table_name, *args, **kwargs: created_tables.append(table_name),
        raising=False,
    )

    mod.upgrade()

    assert created_tables == [
        "c7_workflows",
        "c7_workflow_executions",
        "c7_execution_tasks",
        "c7_execution_events",
    ]
    assert any(
        "CREATE INDEX IF NOT EXISTS idx_c7_execution_task_status_created" in sql
        for sql in executed_sql
    )
