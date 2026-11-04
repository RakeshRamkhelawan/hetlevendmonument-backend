"""Acceptant ronde 3, N2: het login-antwoord draagt dezelfde rechten als `/auth/me`.

De frontend vult zijn store uit het login-antwoord. Daar stond `permissions: []`, dus direct na
het inloggen zag niemand een schrijfknop; pas na een `/auth/me` wel.

Echt: de route `/api/v1/auth/token` met wachtwoordcontrole, Postgres (netwerkpoort 5455) en de
rollen en `role_permissions` van de gezaaide beheerder. Niets aan de loginkant is vervangen.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

_ADMIN_EMAIL = "admin@integration.test"
_ADMIN_PASS = "AdminPass123!"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_login_answer_carries_the_same_permissions_as_me(
    integration_client: AsyncClient,
) -> None:
    login = await integration_client.post(
        "/api/v1/auth/token",
        data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASS, "grant_type": "password"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = await integration_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me.status_code == 200, me.text

    rechten = login.json()["user"]["permissions"]
    assert rechten, "het login-antwoord geeft een lege rechtenlijst"
    assert rechten == me.json()["permissions"]
