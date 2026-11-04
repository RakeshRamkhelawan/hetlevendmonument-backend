"""SP-DSM-002 Groep C: violation-wachters per deferred bestand.

Status na Dag 3 (2026-06-16):
- api/learning.py: GROEN -- Strangler Fig migratie Dag 2
- api/main.py: GROEN -- scanner-exempt (bootstrap entry point, geen v1/-domein)
- api/setup/lifecycle.py: GROEN -- scanner-exempt (startup/lifespan code, geen v1/-domein)
- _prana_contracts_cache.py: GROEN via scanner-exempt, maar 3 ALS-violations nog aanwezig
  (zie test_prana_contracts_cache_als_violations_pending_adr hieronder)
"""

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]
_PRANA_CACHE = _REPO_ROOT / "src" / "core" / "api" / "v1" / "_prana_contracts_cache.py"


def test_api_learning_py_violations_zero() -> None:
    """api/learning.py mag geen ADR-033 violations meer hebben -- gefixed in SP-DSM-002 Dag 2."""
    from scripts.dsm_api_violation_finder import find_violations

    v = [str(p) for p, _, _ in find_violations() if "api/learning.py" in str(p).replace("\\", "/")]
    assert len(v) == 0, f"src/core/api/learning.py: {len(v)} violations resterend"


def test_api_main_py_violations_zero() -> None:
    from scripts.dsm_api_violation_finder import find_violations

    v = [str(p) for p, _, _ in find_violations() if "api/main.py" in str(p).replace("\\", "/")]
    assert len(v) == 0, f"src/core/api/main.py: {len(v)} violations resterend"


def test_api_lifecycle_py_violations_zero() -> None:
    from scripts.dsm_api_violation_finder import find_violations

    v = [
        str(p) for p, _, _ in find_violations() if "setup/lifecycle.py" in str(p).replace("\\", "/")
    ]
    assert len(v) == 0, f"src/core/api/setup/lifecycle.py: {len(v)} violations resterend"


def test_prana_contracts_cache_violations_zero() -> None:
    from scripts.dsm_api_violation_finder import find_violations

    v = [str(p) for p, _, _ in find_violations() if "_prana_contracts_cache" in str(p)]
    assert len(v) == 0, f"_prana_contracts_cache.py: {len(v)} violations resterend"


def test_board_router_violations_zero() -> None:
    """company/board_router.py mag geen ADR-033 violations meer hebben -- gefixed in SP-DSM-002 Dag 5."""
    from scripts.dsm_api_violation_finder import find_violations

    v = [str(p) for p, _, _ in find_violations() if "board_router.py" in str(p).replace("\\", "/")]
    assert len(v) == 0, f"company/board_router.py: {len(v)} violations resterend"


def test_prana_contracts_cache_als_violations_pending_adr() -> None:
    """ALS-violations in _prana_contracts_cache.py zijn gefixed (SP-DSM-002 Dag 5)."""
    assert _PRANA_CACHE.exists(), (
        f"{_PRANA_CACHE} bestaat niet meer. Hernoemd of verplaatst? Deze test controleert "
        "dan NIETS meer -- werk het pad hierboven bij in plaats van de test te laten slagen."
    )
    tree = ast.parse(_PRANA_CACHE.read_text(encoding="utf-8", errors="ignore"))
    als_imports = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("src.core.als")
    ]
    assert len(als_imports) == 0, f"ALS-violations aanwezig ({len(als_imports)}): {als_imports}"
