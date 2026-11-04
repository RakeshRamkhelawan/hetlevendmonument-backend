"""Regression tests for offline-safe Alembic migrations in CI dry-runs."""

import importlib.util
import sys
import types
from pathlib import Path


def _load_module(module_name: str, migration_path: str):
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = types.SimpleNamespace(create_table=None, execute=None, get_bind=None)
    fake_alembic.context = types.SimpleNamespace(is_offline_mode=lambda: False)
    sys.modules["alembic"] = fake_alembic

    path = Path(migration_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None, f"Migration file not found at {path}"
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_c7_rls_upgrade_offline_skips_inspection(monkeypatch) -> None:
    """C7 RLS migration must not inspect MockConnection-backed binds in offline mode."""
    mod = _load_module(
        "c7_rls_migration_20260523c",
        "src/alembic/versions/20260523c_add_rls_c7_workflow_tables.py",
    )
    executed: list[str] = []

    class _FakeBind:
        class dialect:
            name = "postgresql"

    monkeypatch.setattr(mod.op, "get_bind", lambda: _FakeBind(), raising=False)
    monkeypatch.setattr(mod, "_is_offline", lambda _: True)
    monkeypatch.setattr(
        mod.sa,
        "inspect",
        lambda *_: (_ for _ in ()).throw(AssertionError("inspect should not run offline")),
    )
    monkeypatch.setattr(mod.op, "execute", lambda stmt: executed.append(str(stmt)), raising=False)

    mod.upgrade()

    assert any("ALTER TABLE c7_workflows ENABLE ROW LEVEL SECURITY" in sql for sql in executed)


def test_persona_upgrade_offline_skips_inspection(monkeypatch) -> None:
    """Persona migration must create tables without inspection in offline mode."""
    mod = _load_module(
        "persona_migration_20260528a",
        "src/alembic/versions/20260528a_add_personas_and_user_persona_preferences.py",
    )
    created_tables: list[str] = []

    monkeypatch.setattr(mod.op, "get_bind", lambda: object(), raising=False)
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
    monkeypatch.setattr(mod.op, "create_index", lambda *args, **kwargs: None, raising=False)

    mod.upgrade()

    assert created_tables == ["personas", "user_persona_preferences"]


def test_documents_upgrade_offline_skips_inspection(monkeypatch) -> None:
    """Documents migration must create table path without offline inspection."""
    mod = _load_module(
        "documents_migration_47ca3df1f5e6",
        "src/alembic/versions/47ca3df1f5e6_extend_documents_table.py",
    )
    created_tables: list[str] = []

    monkeypatch.setattr(mod.op, "get_bind", lambda: object(), raising=False)
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
    monkeypatch.setattr(mod.op, "create_index", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(mod.op, "execute", lambda *args, **kwargs: None, raising=False)

    mod.upgrade()

    assert created_tables == ["documents"]
