import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration]


async def test_canvases_table_exists_after_upgrade(postgres_session: AsyncSession) -> None:
    """
    CG-002: Verifieer dat de canvases tabel bestaat in de DB na alembic upgrade head.
    ROOD: voor de migratie -- ProgrammingError: relation "canvases" does not exist
    GROEN: na de migratie
    """
    result = await postgres_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_name = 'canvases'")
    )
    row = result.fetchone()
    assert row is not None, "canvases tabel ontbreekt -- voer alembic upgrade head uit"
    assert row[0] == "canvases"


async def test_all_canvas_tables_exist(postgres_session: AsyncSession) -> None:
    """Alle 5 canvas-tabellen bestaan na migratie."""
    expected = {
        "canvases",
        "canvas_blocks",
        "canvas_connections",
        "canvas_collaborators",
        "canvas_operations",
    }
    result = await postgres_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = ANY(:names)"
        ),
        {"names": list(expected)},
    )
    found = {row[0] for row in result.fetchall()}
    missing = expected - found
    assert not missing, f"Ontbrekende canvas-tabellen: {missing}"


async def test_canvases_tenant_id_not_null(postgres_session: AsyncSession) -> None:
    """tenant_id kolom is NOT NULL (ADR-005 vereiste)."""
    result = await postgres_session.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'canvases' AND column_name = 'tenant_id'"
        )
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] == "NO", "tenant_id MOET NOT NULL zijn (ADR-005)"
