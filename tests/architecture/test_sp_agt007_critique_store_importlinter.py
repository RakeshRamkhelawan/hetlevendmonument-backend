"""Architecture test: CritiqueStore Cat B imports aanwezig in .importlinter.

SP-AGT-007 FA-001: critique_store -> tool_broker.hitl_repository whitelist ontbrak.
Deze test voorkomt dat toekomstige cleanup de Cat B entries verwijdert.
"""

from pathlib import Path


def _importlinter_content() -> str:
    return Path(".importlinter").read_text(encoding="utf-8")


def test_critique_store_hitl_repository_in_importlinter() -> None:
    """Cat B whitelist critique_store -> tool_broker.hitl_repository MOET in .importlinter staan."""
    content = _importlinter_content()
    assert "critique_store -> src.core.tool_broker.hitl_repository" in content, (
        "SP-AGT-007: critique_store -> tool_broker.hitl_repository ontbreekt in .importlinter Cat B whitelist"
    )


def test_critique_store_best_effort_in_importlinter() -> None:
    """Cat B whitelist critique_store -> utils.best_effort MOET in .importlinter staan."""
    content = _importlinter_content()
    assert "critique_store -> src.core.utils.best_effort" in content, (
        "SP-AGT-006: critique_store -> utils.best_effort ontbreekt in .importlinter Cat B whitelist"
    )


def test_critique_store_database_in_importlinter() -> None:
    """Cat B whitelist critique_store -> database MOET in .importlinter staan."""
    content = _importlinter_content()
    assert "critique_store -> src.core.database.database" in content, (
        "SP-AGT-005: critique_store -> database.database ontbreekt in .importlinter Cat B whitelist"
    )
