"""Regression tests for scripts/dsm_full_analysis.py scanner fixes.

Covers:
- Double-prefix normalization (src.core.src.* -> src.*)
- Mapping of previously unclassified modules
- Loose file support in SOURCE_DIRS
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.dsm_full_analysis import classify, scan_module, MODULE_MAP


@pytest.mark.architecture
def test_no_double_prefix_artifacts_in_dsm() -> None:
    """Relatieve imports mogen geen 'src.core.src.' prefix achterlaten."""
    # This is the artifact produced before normalization.
    assert classify("src.core.src.config") is None

    # After normalization the same module resolves as shared config (reclassified SP-DSM-008).
    normalized = "src.core.src.config".replace("src.core.src.", "src.")
    assert classify(normalized) == "shared"


@pytest.mark.architecture
def test_scan_module_normalizes_double_prefix() -> None:
    """scan_module() must normalize src.core.src.* before classification."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "dummy.py"
        source.write_text(
            "from src.core.src.config import SETTINGS\nfrom src.core.src.main import app\n",
            encoding="utf-8",
        )
        counts, files, unclassified = scan_module("tenancy", [tmp])

    assert files == 1
    assert unclassified.get("src") is None
    assert counts.get("shared") == 1  # src.config reclassified shared in SP-DSM-008
    assert counts.get("core_api") == 1


@pytest.mark.architecture
def test_scan_module_accepts_loose_files() -> None:
    """scan_module() must accept a single file path in SOURCE_DIRS."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "loose.py"
        source.write_text(
            "from src.core.container import Container\n",
            encoding="utf-8",
        )
        counts, files, unclassified = scan_module("infra", [str(source)])

    assert files == 1
    assert counts.get("infra") is None  # infra importing infra is ignored
    assert len(unclassified) == 0


@pytest.mark.architecture
@pytest.mark.parametrize(
    "module,bucket",
    [
        (
            "src.core.container",
            "shared",
        ),  # SP-DSM-014: reclassified to shared (DI container, niet agent_runtime logic)
        ("src.domains.canvas", "domain_pack"),
        ("src.domains.memory", "agent_runtime"),
        ("src.domains.flows", "agent_runtime"),
        ("src.domains.documents", "domain_pack"),
        ("src.domains.agentic", "agent_runtime"),
        ("src.core.dependencies", "core_api"),
        ("src.domains.projects", "domain_pack"),
    ],
)
def test_unclassified_modules_are_mapped(module: str, bucket: str | None) -> None:
    """Modules identified in the DSM audit must map to a non-None bucket."""
    assert module in MODULE_MAP, f"{module} missing from MODULE_MAP"
    assert classify(module) == bucket
    assert classify(f"{module}.something") == bucket
