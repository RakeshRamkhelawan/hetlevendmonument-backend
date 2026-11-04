"""`router_debug`: de tenant komt uit de JWT, nooit uit de querystring (brief 2026-10-20, CLAUDE.md NOOIT-lijst).

Gate 2 (2026-10-19) vond dat `/test`, `/stats` en `/heatmap` een `tenant_id` uit de querystring namen, zonder
authenticatie. `/test` is op 2026-10-19 al omgezet; `/stats` en `/heatmap` nu ook, en `/test` krijgt een limiet
op het aantal queries (elke query loopt door de routering, en daarmee door een taalmodel).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.agentic.router_debug import router
from src.core.auth.api_deps import get_current_user


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, tenant_id=5)
    return TestClient(app)


def _pad(client: TestClient, eind: str) -> str:
    """Het voorvoegsel van de router, zonder het hier vast te leggen."""
    return next(r.path for r in client.app.routes if r.path.endswith(eind))  # type: ignore[attr-defined]


def test_de_heatmap_toont_de_tenant_van_de_gebruiker_en_negeert_de_querystring(
    client: TestClient,
) -> None:
    antwoord = client.get(_pad(client, "/heatmap"), params={"tenant_id": "999"})

    assert (antwoord.status_code, antwoord.json()["tenant_id"]) == (200, "5")


def test_stats_heeft_geen_tenant_id_parameter_meer() -> None:
    import inspect

    from src.core.api.v1.agentic.router_debug import get_routing_stats

    assert "tenant_id" not in inspect.signature(get_routing_stats).parameters


def test_stats_en_heatmap_vereisen_een_ingelogde_gebruiker() -> None:
    app = FastAPI()
    app.include_router(router)

    routes = [r for r in app.routes if r.path.endswith(("/stats", "/heatmap"))]  # type: ignore[attr-defined]
    beveiligd = [
        any(d.call is get_current_user for d in r.dependant.dependencies)  # type: ignore[attr-defined]
        for r in routes
    ]

    assert beveiligd == [True, True]


def test_test_weigert_meer_dan_twintig_queries(client: TestClient) -> None:
    antwoord = client.post(_pad(client, "/test"), json=[f"vraag {i}" for i in range(21)])

    assert antwoord.status_code == 422


def test_test_weigert_een_te_lange_query(client: TestClient) -> None:
    antwoord = client.post(_pad(client, "/test"), json=["x" * 1001])

    assert antwoord.status_code == 422
