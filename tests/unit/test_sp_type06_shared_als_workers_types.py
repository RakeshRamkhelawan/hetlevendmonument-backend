"""
SP-TYPE-06 -- AST regression tests for shared/llm_client.py and
als/models/collective_knowledge.py type hardening.

One test per file with a meaningful concrete-type replacement.  Uses only
stdlib AST so no production imports are triggered at collection time.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # repo root


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _parse(rel: str) -> ast.Module:
    path = ROOT / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# ---------------------------------------------------------------------------
# 1. llm_client.py -- get_metrics return narrowed from dict[str, Any] to
#    dict[str, str | int | float]
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_llm_client_get_metrics_return_type_narrowed() -> None:
    """get_metrics must return dict[str, str | int | float], not dict[str, Any]."""
    src = _source("src/core/shared/llm_client.py")

    # Concrete union must be present
    assert "dict[str, str | int | float]" in src, (
        "get_metrics() return type should be dict[str, str | int | float] in llm_client.py"
    )

    # The old generic form should not appear on the get_metrics signature line
    for line in src.splitlines():
        if "def get_metrics" in line:
            assert "dict[str, Any]" not in line, (
                "get_metrics() should no longer return dict[str, Any]; found: " + line.strip()
            )
            break


# ---------------------------------------------------------------------------
# 2. collective_knowledge.py -- EmbeddingType base narrowed to
#    TypeDecorator[list[float]]; embedding field typed as list[float] | None
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_collective_knowledge_embedding_type_narrowed() -> None:
    """EmbeddingType must extend TypeDecorator[list[float]], not TypeDecorator[Any]."""
    src = _source("src/core/als/models/collective_knowledge.py")

    # Base class must use concrete type param
    assert "TypeDecorator[list[float]]" in src, (
        "EmbeddingType should extend TypeDecorator[list[float]] in collective_knowledge.py"
    )

    # Must NOT use the old bare Any param
    assert "TypeDecorator[Any]" not in src, (
        "TypeDecorator[Any] should have been replaced by TypeDecorator[list[float]] "
        "in collective_knowledge.py"
    )


@pytest.mark.unit
def test_collective_knowledge_embedding_field_narrowed() -> None:
    """embedding ORM field must be Mapped[list[float] | None], not Mapped[Any | None]."""
    src = _source("src/core/als/models/collective_knowledge.py")

    assert "Mapped[list[float] | None]" in src, (
        "embedding field should be typed as Mapped[list[float] | None] in collective_knowledge.py"
    )

    assert "Mapped[Any | None]" not in src, (
        "Mapped[Any | None] should have been replaced for the embedding field "
        "in collective_knowledge.py"
    )
