"""Ongeldige invoer op `/agentic/experiments/` geeft 400, geen 500 (ADR-036 OP-135).

**De bevinding.** `create_experiment` roept de service aan zonder `ValueError` af te vangen. De
validatie in `production_integration._validate_test_config` gooit die wel -- bijvoorbeeld
"Minimum sample size should be at least 100 for statistical validity". Gevolg in CI-run
31615480686:

    ERROR src.core.exceptions.handlers: Unhandled exception on POST /api/v1/agentic/experiments/:
    ValueError: Minimum sample size should be at least 100 for statistical validity

Dat is een 500 met een volledige stacktrace in de log, terwijl `.claude/rules/error-handling.md`
voor ongeldige invoer een 400 voorschrijft en geen stacktraces in productie wil. De aanroeper
krijgt "Internal server error" en hoort dus niet wat hij fout deed, terwijl er niets kapot is.

Dit raakt ELKE validatiefout op dit pad, niet alleen de steekproefgrens: dezelfde functie gooit
`ValueError` voor onbekende varianten en voor een verkeerde verkeersverdeling.

**Waarom deze test in `tests/unit` staat en niet bij de integratietests.** Het bestand
`tests/integration/agentic/test_experiment_api.py` heeft een `skipif(sys.platform == "win32")`
wegens een ProactorEventLoop-deadlock. Daar kan de roodheid dus niet lokaal bewezen worden -- en
precies dat liet vandaag drie fouten in dat bestand onopgemerkt tot CI ze vond. Deze test gebruikt
alleen dependency-overrides en draait overal.

**Mutatietest (2026-08-12, beide richtingen):**

1. De `except ValueError`-tak uit `experiments.py` weghalen -> ROOD (500 in plaats van 400).
2. De andere kant: een geslaagde aanroep geeft nog steeds 201
   (`test_a_valid_request_still_creates`). Zonder die helft zou "geef altijd 400" een geldige
   oplossing zijn en was het endpoint stuk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.exceptions import ValidatieFout
from src.domains.agentic.api import experiments as experiments_module
from src.domains.agentic.api.dependencies import get_experimentation_service

_PAYLOAD = {
    "name": "API Experiment",
    "description": "Testing API creation",
    "prompt_template_id": 1,
    "variants": [
        {"name": "Control", "content": "C", "traffic": 0.5, "is_control": True},
        {"name": "Variant B", "content": "B", "traffic": 0.5, "is_control": False},
    ],
    "min_sample_size": 50,
}


def _app(service: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(experiments_module.router)

    gebruiker = MagicMock()
    gebruiker.tenant_id = 1
    gebruiker.id = 1

    app.dependency_overrides[get_experimentation_service] = lambda: service
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_current_user] = lambda: gebruiker
    return app


@pytest.mark.asyncio
async def test_a_rejected_sample_size_is_a_client_error() -> None:
    """De kern: onze eigen validatie mag geen 500 opleveren."""
    service = MagicMock()
    service.create_experiment = AsyncMock(
        side_effect=ValidatieFout(
            "Minimum sample size should be at least 100 for statistical validity"
        )
    )

    transport = ASGITransport(app=_app(service))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/agentic/experiments/", json=_PAYLOAD)

    assert response.status_code == 400, (
        f"Ongeldige invoer geeft {response.status_code} in plaats van 400. De aanroeper krijgt dan "
        f"'Internal server error' en hoort niet wat hij fout deed, terwijl er niets kapot is. "
        f"Antwoord: {response.text}"
    )
    assert "sample size" in response.text.lower(), (
        f"De 400 vertelt niet WAT er mis is. Antwoord: {response.text}"
    )


@pytest.mark.asyncio
async def test_a_foreign_value_error_does_not_reach_the_client() -> None:
    """Een ValueError van een bibliotheek is geen eigen validatietekst (brief 2026-10-21)."""
    service = MagicMock()
    service.create_experiment = AsyncMock(
        side_effect=ValueError("bad url http://db-intern.example:5432/x")
    )

    transport = ASGITransport(app=_app(service))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/agentic/experiments/", json=_PAYLOAD)

    assert response.status_code == 400 and "db-intern.example" not in response.text


@pytest.mark.asyncio
async def test_a_valid_request_still_creates() -> None:
    """De andere richting -- anders zou 'geef altijd 400' een geldige oplossing zijn."""
    service = MagicMock()
    service.create_experiment = AsyncMock(return_value=42)

    app = _app(service)

    # Een echt object en geen MagicMock: `ExperimentResponse` valideert de velden, en een
    # MagicMock levert daar attributen op die geen `str` zijn -- dan faalt de responsvalidatie en
    # meet deze test iets anders dan wat hij beweert.
    class _Experiment:
        id = "42"
        name = "API Experiment"
        description = "Testing API creation"
        status = "active"
        start_time = datetime(2026, 8, 12, tzinfo=timezone.utc)
        end_time = None
        prompt_template_id = 1

    gemaakt = _Experiment()

    repo = MagicMock()
    repo.get_experiment = AsyncMock(return_value=gemaakt)
    experiments_module.SQLAlchemyPromptRepository = MagicMock(return_value=repo)  # type: ignore[misc]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/agentic/experiments/", json=_PAYLOAD)

    assert response.status_code != 400, (
        "Een geldige aanroep krijgt ook een 400 -- dan is 'weiger alles' de oplossing geworden en "
        f"is het endpoint stuk. Antwoord: {response.text}"
    )
