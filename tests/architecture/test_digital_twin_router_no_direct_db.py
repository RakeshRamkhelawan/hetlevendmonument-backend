"""Architecture test: digital_twin domain moet bestaan en service injection gebruiken.

TODO(AUDIT-DB14b): DigitalTwinService + src/core/api/v1/digital_twin/ aanmaken.
"""

import ast
from pathlib import Path


def test_digital_twin_router_exists() -> None:
    """AUDIT-DB14b: src/core/api/v1/digital_twin/router.py moet aanwezig zijn."""
    router_file = Path("src/core/api/v1/digital_twin/router.py")
    assert router_file.exists(), (
        "src/core/api/v1/digital_twin/router.py ontbreekt (AUDIT-DB14b). "
        "Maak het digital_twin domein aan met DigitalTwinService via Depends()."
    )


def test_digital_twin_router_no_direct_db_imports() -> None:
    """AUDIT-DB14b: digital_twin/router.py mag geen directe DB-imports bevatten."""
    FORBIDDEN = {"get_db", "AsyncSession", "select", "func", "update", "delete"}
    router_file = Path("src/core/api/v1/digital_twin/router.py")
    assert router_file.exists(), "src/core/api/v1/digital_twin/router.py ontbreekt"

    tree = ast.parse(router_file.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imported.add(alias.name)
                if alias.asname:
                    imported.add(alias.asname)

    violations = FORBIDDEN & imported
    assert not violations, (
        f"digital_twin/router.py importeert verboden DB-symbolen: {violations}. "
        "Gebruik Depends(get_digital_twin_service) in plaats van Depends(get_db)."
    )


def test_digital_twin_service_exists() -> None:
    """AUDIT-DB14b: digital_twin/service.py moet aanwezig zijn."""
    service_file = Path("src/core/api/v1/digital_twin/service.py")
    assert service_file.exists(), "src/core/api/v1/digital_twin/service.py ontbreekt (AUDIT-DB14b)."


def test_digital_twin_dependencies_exists() -> None:
    """AUDIT-DB14b: digital_twin/dependencies.py met get_digital_twin_service factory."""
    deps_file = Path("src/core/api/v1/digital_twin/dependencies.py")
    assert deps_file.exists(), (
        "src/core/api/v1/digital_twin/dependencies.py ontbreekt (AUDIT-DB14b)."
    )
    content = deps_file.read_text(encoding="utf-8")
    assert "get_digital_twin_service" in content, (
        "get_digital_twin_service factory ontbreekt in digital_twin/dependencies.py"
    )
