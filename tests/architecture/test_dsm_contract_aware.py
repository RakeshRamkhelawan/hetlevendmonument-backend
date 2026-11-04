"""Tests for scripts/dsm_contract_aware_analysis.py.

Verifies that the contract-aware DSM scanner correctly classifies imports
as allowed, exempt, or violation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dsm_contract_aware_analysis import (
    ALLOWED_EDGES,
    LEGACY_FLAT_ENDPOINTS,
    _is_allowed,
    classify_import,
    parse_ignore_imports,
)

_REPO_ROOT = Path(__file__).parents[2]


@pytest.mark.architecture
def test_parse_ignore_imports_reads_dot_importlinter() -> None:
    """ignore_imports must be populated from .importlinter."""
    assert len(ALLOWED_EDGES) > 0, "No allowed edges parsed from .importlinter"
    assert ("src", "src.workers") in ALLOWED_EDGES


@pytest.mark.architecture
def test_allowed_edge_exact_match() -> None:
    """Exact module pairs in ignore_imports are allowed."""
    assert _is_allowed("src", "src.workers") is True


@pytest.mark.architecture
def test_allowed_edge_prefix_match() -> None:
    """Descendant modules of an allowed edge are allowed."""
    assert _is_allowed("src.core.api.dependencies", "src.core.database.database") is True


@pytest.mark.architecture
def test_unallowed_edge_is_violation() -> None:
    """Imports not in ignore_imports are violations."""
    assert _is_allowed("src.core.api.v1.foo.router", "src.core.agents.agent_registry") is False


@pytest.mark.architecture
def test_legacy_flat_endpoint_is_exempt() -> None:
    """Legacy *_endpoints.py files are classified as exempt."""
    path = _REPO_ROOT / "src" / "core" / "api" / "admin_endpoints.py"
    assert LEGACY_FLAT_ENDPOINTS.search(str(path)) is not None
    result = classify_import(path, "src.core.api.admin_endpoints", "src.core.database.database")
    assert result == "exempt"


@pytest.mark.architecture
def test_non_legacy_non_allowed_is_violation() -> None:
    """A non-legacy file with a non-allowed import is a violation."""
    path = _REPO_ROOT / "src" / "core" / "api" / "v1" / "foo" / "router.py"
    result = classify_import(path, "src.core.api.v1.foo.router", "src.core.agents.agent_registry")
    assert result == "violation"
