import pytest

pytestmark = pytest.mark.unit


def test_canvas_model_uses_main_base() -> None:
    """Canvas moet erven van de hoofd-Base, niet van een gesoleerde CanvasBase."""
    from src.core.database.database import Base
    from src.domains.canvas.models import Canvas

    assert issubclass(Canvas, Base), (
        "Canvas erft nog van CanvasBase -- migreer naar hoofd-Base per CG-002"
    )


def test_canvas_tables_in_alembic_metadata() -> None:
    """Alle 5 canvas-tabellen moeten in Base.metadata zitten voor Alembic."""
    from src.core.database.database import Base
    from src.core.database.model_registry import register_all_models

    register_all_models()

    expected_tables = {
        "canvases",
        "canvas_blocks",
        "canvas_connections",
        "canvas_collaborators",
        "canvas_operations",
    }
    registered = set(Base.metadata.tables.keys())
    missing = expected_tables - registered
    assert not missing, (
        f"Canvas-tabellen ontbreken in Base.metadata: {missing}. "
        "Voeg domains.canvas toe aan model_registry.py"
    )


def test_canvas_tenant_id_is_not_nullable() -> None:
    """Canvas.tenant_id kolom is NOT NULL per ADR-005."""
    from src.domains.canvas.models import Canvas

    col = Canvas.__table__.columns["tenant_id"]
    assert not col.nullable, "Canvas.tenant_id MOET NOT NULL zijn (ADR-005)"
