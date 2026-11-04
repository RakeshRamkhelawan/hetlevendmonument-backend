"""Gebruikersbeheer: de ECHTE vorm van het antwoord en wat Deactiveren met rollen doet.

Aanleiding (acceptatie 2026-10-10, scenario 6): na Deactiveren zou de rollenlijst van de
gebruiker leeg zijn. Deze tests meten tegen de echte app en de testdatabase wat de route doet.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import (  # noqa: F401
    AANVRAGER,
    COLLEGA,
    _sql,
    _zet_rollen,
    rollen_hersteld,
)
from tests.integration.test_laatste_beheerder import (  # noqa: F401
    _aanroep,
    _token_van,
    beheerders_geisoleerd,
)


async def _rollen_van(user_id: int) -> list[str]:
    rijen = (
        await _sql(
            "SELECT r.name FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
            "WHERE ur.user_id = :u ORDER BY r.name",
            u=user_id,
        )
    ).all()
    return [str(r[0]) for r in rijen]


@pytest.mark.integration
@pytest.mark.asyncio
class TestGebruikerslijstEnDeactiveren:
    async def test_the_list_gives_roles_as_objects_with_id_and_name(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin", "goedkeurder"])

        antwoord = await _aanroep(
            integration_app, await _token_van(AANVRAGER), "GET", "/api/v1/users/"
        )

        rijen = {r["id"]: r for r in antwoord.json()["data"]}
        assert sorted(rol["name"] for rol in rijen[COLLEGA]["roles"]) == ["admin", "goedkeurder"]

    async def test_deactivating_with_only_is_active_keeps_the_roles_in_the_database(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin", "goedkeurder"])

        antwoord = await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "PUT",
            f"/api/v1/users/{COLLEGA}",
            {"is_active": False},
        )

        assert antwoord.status_code == 200, antwoord.text
        assert await _rollen_van(COLLEGA) == ["admin", "goedkeurder"]

    async def test_the_put_response_itself_still_lists_the_roles(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin", "goedkeurder"])

        antwoord = await _aanroep(
            integration_app,
            await _token_van(AANVRAGER),
            "PUT",
            f"/api/v1/users/{COLLEGA}",
            {"is_active": False},
        )

        assert sorted(rol["name"] for rol in antwoord.json()["roles"]) == ["admin", "goedkeurder"]

    async def test_the_list_after_deactivating_still_shows_the_roles(
        self, beheerders_geisoleerd: None, integration_app: Any
    ) -> None:
        await _zet_rollen(AANVRAGER, ["admin"])
        await _zet_rollen(COLLEGA, ["admin", "goedkeurder"])
        token = await _token_van(AANVRAGER)
        await _aanroep(
            integration_app, token, "PUT", f"/api/v1/users/{COLLEGA}", {"is_active": False}
        )

        antwoord = await _aanroep(integration_app, token, "GET", "/api/v1/users/")

        rijen = {r["id"]: r for r in antwoord.json()["data"]}
        assert sorted(rol["name"] for rol in rijen[COLLEGA]["roles"]) == ["admin", "goedkeurder"]
