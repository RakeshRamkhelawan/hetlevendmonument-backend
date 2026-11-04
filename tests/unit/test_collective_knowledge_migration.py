"""Regression tests for collective knowledge migration offline mode."""

import importlib.util
import sys
import types
from pathlib import Path


_MIGRATION_PATH = Path(
    "src/alembic/versions/20260509_add_extra_metadata_to_collective_knowledge.py"
)
_MODULE_NAME = "collective_knowledge_migration_20260509"


def _load_module():
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = types.SimpleNamespace(get_bind=None, execute=None)
    fake_alembic.context = types.SimpleNamespace(is_offline_mode=lambda: False)
    sys.modules["alembic"] = fake_alembic

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MIGRATION_PATH)
    assert spec is not None, f"Migration file not found at {_MIGRATION_PATH}"
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_upgrade_offline_emits_alter_table(monkeypatch) -> None:
    """Offline upgrade must emit idempotent ALTER SQL without table inspection."""
    mod = _load_module()
    executed: list[str] = []

    monkeypatch.setattr(mod.op, "get_bind", lambda: object(), raising=False)
    monkeypatch.setattr(mod, "_is_offline", lambda _: True)
    monkeypatch.setattr(
        mod,
        "_table_exists",
        lambda *_: (_ for _ in ()).throw(AssertionError("_table_exists should not run offline")),
    )
    monkeypatch.setattr(mod.op, "execute", executed.append, raising=False)

    mod.upgrade()

    assert executed == [
        "ALTER TABLE collective_knowledge ADD COLUMN IF NOT EXISTS extra_metadata JSON"
    ]


def test_downgrade_offline_emits_drop_column(monkeypatch) -> None:
    """Offline downgrade must emit DROP COLUMN SQL without table inspection."""
    mod = _load_module()
    executed: list[str] = []

    monkeypatch.setattr(mod.op, "get_bind", lambda: object(), raising=False)
    monkeypatch.setattr(mod, "_is_offline", lambda _: True)
    monkeypatch.setattr(
        mod,
        "_table_exists",
        lambda *_: (_ for _ in ()).throw(AssertionError("_table_exists should not run offline")),
    )
    monkeypatch.setattr(mod.op, "execute", executed.append, raising=False)

    mod.downgrade()

    assert executed == ["ALTER TABLE collective_knowledge DROP COLUMN IF EXISTS extra_metadata"]
