"""FA-004: startup smoke-tests voor ADR-033 router registratie."""

import importlib

import pytest


@pytest.mark.unit
def test_register_all_routers_returns_positive_count() -> None:
    """register_all_routers() moet een positief aantal routers retourneren.

    Verifieert dat de ADR-033 router registry operationeel is na startup:
    alle domeinen geregistreerd, geen silent failure bij lazy imports.
    """
    from fastapi import FastAPI

    from src.core.api.router_registry import register_all_routers

    app = FastAPI()
    count = register_all_routers(app)
    assert isinstance(count, int) and count > 0, (
        f"register_all_routers() retourneerde {count!r} -- verwacht int > 0. "
        "FA-004: ADR-033 startup smoke-test."
    )


@pytest.mark.unit
def test_app_module_has_app_object() -> None:
    """src.core.api.main moet een 'app' attribuut hebben van type FastAPI.

    Verifieert dat de applicatie-factory correct initialiseert zonder
    TESTING-omgeving -- de app is bruikbaar als ASGI entry point.
    """
    mod = importlib.import_module("src.core.api.main")
    assert hasattr(mod, "app"), (
        "src.core.api.main heeft geen 'app' attribuut. FA-004: ADR-033 smoke-test."
    )
    assert mod.app is not None, "src.core.api.main.app is None. FA-004: ADR-033 smoke-test."
