"""Acceptant ronde 3, N4: `/api/v1/autonomous/*` gaf 500 in plaats van een nette 503.

`get_agent_factory()` geeft `None`: `create_agent_factory()` wordt bij het opstarten nergens
aangeroepen, ook niet in de geschiedenis (`git log -S create_agent_factory` op `main.py`,
`app_lifespan.py` en `api/setup/lifecycle.py` is leeg; die laatste roept `get_agent_factory()`
aan en faalde dus ook altijd). Het domein staat sinds ADR-036 D12.5 (OP-162) in de wacht: elke
schrijvende route geeft 503 "pending a governance review", en de factory kent geen `tenant_id`.
Daarom GEEN factory bij het opstarten maar een eerlijke 503. De buitenste `except Exception`
pakte die 503 in tot een 500.

Echt: de app (`register_all_routers`), de ECHTE login als gezaaide beheerder, het token dat die
uitgeeft, de rol- en scopecontrole tegen Postgres (netwerkpoort 5455), en de echte
`get_agent_factory()` -- die eerst aantoonbaar `None` is.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

ROUTES = [
    "/api/v1/autonomous/status",
    "/api/v1/autonomous/agents/templates",
    "/api/v1/autonomous/agents/factory/metrics",
]


def test_the_factory_is_really_absent() -> None:
    from src.core.subagents.agent_factory import get_agent_factory

    assert get_agent_factory() is None


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("pad", ROUTES)
async def test_an_absent_factory_gives_a_clean_503(
    integration_client: AsyncClient, pad: str
) -> None:
    from src.core.subagents.agent_factory import get_agent_factory

    assert get_agent_factory() is None
    login = await integration_client.post(
        "/api/v1/auth/token",
        data={
            "username": "admin@integration.test",
            "password": "AdminPass123!",
            "grant_type": "password",
        },
    )
    assert login.status_code == 200, login.text

    antwoord = await integration_client.get(
        pad, headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )

    assert (antwoord.status_code, antwoord.json().get("detail")) == (
        503,
        "Agent factory not available",
    ), antwoord.text
