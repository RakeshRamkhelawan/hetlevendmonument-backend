"""Smoke Test Suite

Quick post-deploy verification of critical paths.

Part of SB-8.2 implementation.

Usage:
    pytest tests/smoke/test_critical_paths.py -v
    TEST_BASE_URL=https://api.example.org pytest tests/smoke/test_critical_paths.py -v

Hernoemd van `check_critical_paths.py` op 2026-08-14: `pyproject.toml` zet
`python_files = "test_*.py"`, dus pytest verzamelde uit dit bestand NUL tests. De
blue-green-stap in `scripts/README_DEPLOYMENT.md` (`pytest tests/smoke/`) draaide daardoor
niets. Zie ADR-036 OP-124.
"""

import os

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8100")  # Port updated from 8000 to 8100

# De drie endpoints die samen de OpenAPI-oppervlakte vormen (src/main.py:125-127).
OPENAPI_SURFACE = ["/docs", "/redoc", "/openapi.json"]


@pytest.fixture(scope="session")
def smoke_target() -> str:
    """Bereikbaarheid van het doelwit, eenmalig vastgesteld.

    Dit bestand heette tot 2026-08-14 `check_critical_paths.py` en werd door pytest nooit
    verzameld. Bij het hernoemen komt het WEL in een volledige `pytest tests`-run terecht,
    en dan staat er niets op de default-poort. Onbereikbaar is daarom geen failure zolang
    niemand dit bewust op een deployment heeft gericht -- maar is `TEST_BASE_URL` gezet, dan
    smoke-test iemand een echte omgeving en is onbereikbaar een harde fout.
    """
    if "TEST_BASE_URL" not in os.environ:
        # Zonder expliciet doelwit is er niets getoetst. Bij een volledige suite-run is skippen
        # juist; in een deploy-context is het een defect -- daar zet de aanroeper SMOKE_STRICT=1,
        # en dan is een vergeten variabele hard rood in plaats van een groene no-op.
        if os.getenv("SMOKE_STRICT") == "1":
            pytest.fail("SMOKE_STRICT=1 maar TEST_BASE_URL ontbreekt: er is niets getoetst")
        pytest.skip("Zet TEST_BASE_URL om een deployment te toetsen")

    doelwit_is_expliciet = True
    try:
        with httpx.Client(base_url=BASE_URL, timeout=5.0) as probe:
            probe.get("/health")
    except httpx.RequestError as exc:
        if doelwit_is_expliciet:
            pytest.fail(f"TEST_BASE_URL={BASE_URL} is onbereikbaar: {exc}")
        pytest.skip(f"Geen server op {BASE_URL}; zet TEST_BASE_URL om een deployment te toetsen")
    return BASE_URL


@pytest.fixture
def client(smoke_target: str):
    """Create HTTP client for smoke tests."""
    # Als contextmanager: de oude versie retourneerde een client die nooit werd gesloten en
    # dat leverde een ResourceWarning per test op.
    with httpx.Client(base_url=smoke_target, timeout=30.0) as http_client:
        yield http_client


@pytest.fixture
def live_server(client: httpx.Client) -> httpx.Client:
    """Positieve controle voordat er iets over 'dicht' beweerd wordt.

    Zonder dit anker slaagt elke "endpoint geeft 4xx"-assertie ook tegen een DODE
    applicatie: een reverse proxy zonder backend geeft op elk pad een 404. De assertie zou
    dan groen staan om precies de verkeerde reden.
    """
    response = client.get("/health/ready")
    assert response.status_code == 200, (
        f"/health/ready gaf HTTP {response.status_code}; de applicatie is niet gereed, dus een "
        "uitspraak over de OpenAPI-oppervlakte zou niets betekenen"
    )
    return client


class TestHealthEndpoints:
    """Smoke tests for health endpoints."""

    def test_health_endpoint(self, client):
        """Test basic health check returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_ready_endpoint(self, client):
        """Test readiness check returns 200 when all dependencies are up."""
        response = client.get("/ready")
        # 200 = ready, 401 = auth required, 503 = dependencies down
        assert response.status_code in [200, 401, 503]


class TestAuthEndpoints:
    """Smoke tests for authentication."""

    def test_auth_token_endpoint_exists(self, client):
        """Test login endpoint responds (even with bad credentials)."""
        response = client.post(
            "/auth/token",
            data={"username": "smoke@test.com", "password": "test"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # Should get 401 (unauthorized) not 404 (not found)
        assert response.status_code in [200, 401, 422]


class TestOpenApiSurfaceIsClosed:
    """De OpenAPI-oppervlakte is niet bereikbaar op een deployment (ADR-036 OP-124).

    Deze tests eisten tot 2026-08-14 een 200 en legden daarmee precies de onveilige
    toestand vast die OP-124 heeft gerepareerd. Er is bewust GEEN omgevingsschakelaar:
    een smoke-test draait per definitie tegen een deployment, en die is nooit
    `development`. De development-kant (docs juist WEL open) wordt deterministisch en
    zonder netwerk getoetst door `tests/architecture/test_docs_disabled_in_prod.py`.
    """

    @pytest.mark.parametrize("endpoint", OPENAPI_SURFACE)
    def test_endpoint_is_not_reachable(self, live_server: httpx.Client, endpoint: str) -> None:
        response = live_server.get(endpoint)

        # Bewust een 4xx-BEREIK en niet exact 404: een reverse proxy of een tussenliggende laag
        # kan een andere 4xx geven. Een 2xx is geen "dicht", en een 5xx ook niet -- dat is een
        # storing, geen hardening.
        assert 400 <= response.status_code < 500, (
            f"{endpoint} gaf HTTP {response.status_code}; verwacht 4xx. Een bereikbaar "
            "OpenAPI-schema legt de volledige API-oppervlakte bloot aan een onauthenticated "
            "verzoek (ADR-036 OP-124)."
        )


def run_smoke_tests():
    """Run smoke tests programmatically."""
    exit_code = pytest.main([__file__, "-v", "--tb=short"])
    return exit_code == 0


if __name__ == "__main__":
    success = run_smoke_tests()
    raise SystemExit(0 if success else 1)
