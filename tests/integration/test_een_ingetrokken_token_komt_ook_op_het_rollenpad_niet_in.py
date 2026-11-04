"""Een ingetrokken token wordt ook op het rollenpad geweigerd (ADR-036 OP-260).

**De naam van dit bestand was tot 2026-09-19 `..._komt_nergens_meer_in.py` en dat beloofde
meer dan gemeten is.** Er zijn minstens vijf verdere authenticatie-ingangen zonder
blacklistcontrole, alle langs de websocketkant, plus een dode derde implementatie in
`auth/auth_bearer.py`. Deze test dekt het HTTP-rollenpad en niets meer.

ADR-036 OP-188 zette de intrekkingscontrole op `_get_user_from_token`, het pad achter
`get_current_user`. De tweede ingang, `get_current_user_id`
(`src/core/auth/dependencies.py:254`), raadpleegt de blacklist NIET -- gemeten 2026-09-18:
`git grep -n is_jti_revoked -- src/` geeft precies twee treffers, de definitie en die ene
aanroeper. Er is geen tweede laag die het alsnog doet.

Dat is geen theoretisch gat: `src/core/api/v1/rbac/roles_router.py:98-101` hangt
`Depends(get_current_user_id)` onder `GET /api/rbac/roles`, en dat zijn de endpoints waarmee
rollen en rechten worden uitgedeeld.

Deze test loopt over de ECHTE producent: een echte app, een echte database, een echt
verzoek. Hij hoort ROOD te zijn tot OP-260 gerepareerd is.
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_een_ingetrokken_token_wordt_ook_op_het_rollenpad_geweigerd(
    async_client, admin_user_with_token
) -> None:
    """Intrekken moet ELKE ingang sluiten, niet alleen die van get_current_user."""
    token = admin_user_with_token["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Het token werkt nu. Zonder deze controle zou een 401 na het intrekken ook door
    #    een heel andere oorzaak kunnen komen en bewijst de test niets.
    voor = await async_client.get("/api/rbac/roles", headers=headers)
    # Bewust == 200 en niet != 401. Een eerdere versie van deze test gebruikte `!= 401`
    # en stond ROOD OM DE VERKEERDE REDEN: het pad was toen `/api/roles`, dat bestaat niet,
    # en een 404 glipt door een `!= 401`-controle heen. De test faalde dan op de laatste
    # assertie en leek het gat te bewijzen terwijl hij alleen een typefout in een URL mat.
    assert voor.status_code == 200, (
        "GET /api/rbac/roles gaf %d in plaats van 200 VOOR het intrekken. Zolang dat niet "
        "klopt meet de assertie onderaan niet de intrekking maar iets anders."
        % voor.status_code
    )

    # 2. Trek het in via de echte endpoint.
    intrekken = await async_client.post(
        "/api/v1/auth/revoke", json={"token": token}, headers=headers
    )
    assert intrekken.status_code == 200, "Intrekken zelf mislukte: %d" % intrekken.status_code
    assert intrekken.json()["revoked"] is True

    # 3. En nu mag het nergens meer in.
    na = await async_client.get("/api/rbac/roles", headers=headers)
    assert na.status_code == 401, (
        "Een INGETROKKEN token werkt nog op GET /api/rbac/roles (status %d). "
        "get_current_user_id raadpleegt de blacklist niet -- ADR-036 OP-260." % na.status_code
    )
