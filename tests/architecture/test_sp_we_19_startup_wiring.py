"""SP-WE-19: ff_manager en request_audit_logs wiring regression guards."""

from pathlib import Path


def test_ff_manager_init_called_in_lifespan() -> None:
    """SP-WE-19: _init_feature_flags moet aangeroepen worden in app_lifespan.py."""
    source = Path("src/core/app_lifespan.py").read_text(encoding="utf-8")
    assert "_init_feature_flags" in source, (
        "SP-WE-19: ff_manager niet gewired in lifespan -- "
        "alle /api/feature-flags/* requests gooien 503."
    )


def test_request_audit_logs_migration_exists() -> None:
    """SP-WE-19: request_audit_logs tabel migratie moet bestaan."""
    versions = list(Path("src/alembic/versions").glob("*.py"))
    names = [f.name for f in versions]
    has_create = any("request_audit_log" in n for n in names)
    assert has_create, (
        "SP-WE-19: geen Alembic migratie voor request_audit_logs tabel. "
        "Maak een migratie aan die de tabel aanmaakt."
    )
