"""DSM-021: shared sub-lagen -- thematische structuur (DSM-ARCH-004).

Baseline 2026-06-26:
  shared fan-in=1148 (Ce=0) -- geen thematische indeling.
  shared.time = src/core/shared/datetime_utils.py (pure stdlib, Ce=0).

Dag 4 toevoeging 2026-06-27:
  shared.utils = unicode_utils.py + unicode_logging.py (pure stdlib, Ce=0).
  docker_utils.py uitgesloten: intra-shared dep vanuit config.py.

Dag 5 toevoeging 2026-06-27:
  shared.types = ai_act_types.py + consent_categories.py (pure stdlib, Ce=0).
  interfaces.py uitgesloten: Ce=2 (imports src.core.types + src.core.shared.agent_context).
"""

from __future__ import annotations

import pytest

from scripts.dsm_full_analysis import MODULES, SOURCE_DIRS, scan_module


@pytest.mark.architecture
def test_dsm021_shared_time_in_modules_list() -> None:
    """shared.time moet aanwezig zijn in MODULES -- SP-DSM-021 dag 3."""
    assert "shared.time" in MODULES, (
        "shared.time ontbreekt in MODULES (scripts/dsm_full_analysis.py). "
        "SP-DSM-021 dag 3 vereist dit als sub-laag."
    )


@pytest.mark.architecture
def test_dsm021_shared_time_ce_is_zero() -> None:
    """shared.time Ce == 0 -- datetime utilities mogen geen src.* imports bevatten.

    Baseline 2026-06-26: src/core/shared/datetime_utils.py importeert alleen
    stdlib (datetime, timezone, typing). Ce=0 is de invariant voor deze sub-laag.
    """
    counts, _, _ = scan_module("shared.time", SOURCE_DIRS.get("shared.time", []))
    ce = sum(counts.values())
    assert ce == 0, (
        f"shared.time Ce = {ce} (verwacht 0). "
        f"Verdeling: {dict(counts)}. "
        "shared.time mag geen src.* imports bevatten -- alleen stdlib."
    )


@pytest.mark.architecture
def test_dsm021_shared_utils_in_modules_list() -> None:
    """shared.utils moet aanwezig zijn in MODULES -- SP-DSM-021 dag 4."""
    assert "shared.utils" in MODULES, (
        "shared.utils ontbreekt in MODULES (scripts/dsm_full_analysis.py). "
        "SP-DSM-021 dag 4 vereist dit als sub-laag."
    )


@pytest.mark.architecture
def test_dsm021_shared_utils_ce_is_zero() -> None:
    """shared.utils Ce == 0 -- string/logging utilities mogen geen src.* imports bevatten.

    Baseline 2026-06-27: unicode_utils.py en unicode_logging.py importeren alleen
    stdlib. Ce=0 is de invariant voor deze sub-laag.
    docker_utils.py is uitgesloten: src.core.shared.config importeert het (intra-shared dep).
    """
    counts, _, _ = scan_module("shared.utils", SOURCE_DIRS.get("shared.utils", []))
    ce = sum(counts.values())
    assert ce == 0, (
        f"shared.utils Ce = {ce} (verwacht 0). "
        f"Verdeling: {dict(counts)}. "
        "shared.utils mag geen src.* imports bevatten -- alleen stdlib."
    )


@pytest.mark.architecture
def test_dsm021_shared_types_in_modules_list() -> None:
    """shared.types moet aanwezig zijn in MODULES -- SP-DSM-021 dag 5."""
    assert "shared.types" in MODULES, (
        "shared.types ontbreekt in MODULES (scripts/dsm_full_analysis.py). "
        "SP-DSM-021 dag 5 vereist dit als sub-laag."
    )


@pytest.mark.architecture
def test_dsm021_shared_types_ce_is_zero() -> None:
    """shared.types Ce == 0 -- type/enum definitions mogen geen src.* imports bevatten.

    Baseline 2026-06-27: ai_act_types.py en consent_categories.py importeren alleen stdlib.
    Ce=0 is de invariant voor deze sub-laag.
    interfaces.py is uitgesloten: Ce=2 (imports src.core.types + src.core.shared.agent_context).
    """
    counts, _, _ = scan_module("shared.types", SOURCE_DIRS.get("shared.types", []))
    ce = sum(counts.values())
    assert ce == 0, (
        f"shared.types Ce = {ce} (verwacht 0). "
        f"Verdeling: {dict(counts)}. "
        "shared.types mag geen src.* imports bevatten -- alleen stdlib."
    )
