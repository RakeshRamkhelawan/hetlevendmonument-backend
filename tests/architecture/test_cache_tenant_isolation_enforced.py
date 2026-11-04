"""
Architecture test: alle cache-sleutels in scope-bestanden MOETEN tenant_id bevatten.
RED voor de fix, GREEN na de fix.
CI-blokkering zodat herhaling permanent uitgesloten is.
SP-SEC-001 TI-001..005
"""

from pathlib import Path

CACHE_FILES = [
    "src/core/caching/cache_layer.py",
    "src/core/knowledge/embedding_service.py",
    "src/core/api/performance_middleware.py",
    "src/core/llm/intelligent_router.py",
    "src/core/company/goal_service.py",
]


def _extract_cache_key_lines(source: str) -> list[str]:
    """Geeft alleen regels terug die cache_key BOUWEN (assignment), niet regels die het als argument gebruiken."""
    keys = []
    for line in source.splitlines():
        stripped = line.strip()
        # Match only lines that assign TO cache_key (not reads/calls like cache.get(cache_key))
        if (
            stripped.startswith("cache_key")
            and "=" in stripped
            and not stripped.startswith("cache_key,")
        ):
            keys.append(stripped)
    return keys


def test_all_cache_keys_contain_tenant_id():
    """Elke cache-sleutel MOET tenant_id bevatten -- SP-SEC-001 TI-001..005.

    TODO(SP-SEC-001): Falende test afdwingen totdat alle cache-sleutels gefixed zijn.
    """
    violations: list[str] = []
    for path_str in CACHE_FILES:
        path = Path(path_str)
        if not path.exists():
            violations.append(f"MISSING FILE: {path_str}")
            continue
        source = path.read_text(encoding="utf-8")
        for key_line in _extract_cache_key_lines(source):
            # Accept tenant_id, tenant, or _tid (our established abbreviation pattern)
            if "tenant_id" not in key_line and "tenant" not in key_line and "_tid" not in key_line:
                violations.append(f"{path_str}: {key_line}")

    assert not violations, (
        f"Cache-sleutels zonder tenant_id gevonden ({len(violations)}):\n"
        + "\n".join(violations)
        + "\nFix: voeg tenant_id toe als prefix in elke cache-sleutel (SP-SEC-001 TI-001..005)."
    )
