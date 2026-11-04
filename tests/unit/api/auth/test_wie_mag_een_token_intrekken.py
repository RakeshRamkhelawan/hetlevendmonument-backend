"""`_mag_token_intrekken`: wie mag welk token intrekken (beveiligingsnazorg, Gate 2 2026-10-15).

Aanvulling op `tests/integration/test_beveiligingsnazorg_tokens.py`, dat over de echte voordeur
loopt maar geen portaaltoken en geen vervormde claims maakt. Hier de randen, zonder database:

- een PORTAALtoken is geen medewerker: `sub` is een `portal_users`-nummer dat in dezelfde reeks ligt
  als `users.id`; zonder deze controle trekt medewerker N het portaaltoken van portaalgebruiker N in;
- een eigen `sub` bij een ANDERE tenant-claim is niet "eigen";
- een niet-numerieke `sub` geeft geen uitzondering maar een weigering.

Mutatiebewijs (2026-10-15): zie de commitboodschap; per test de mutatie die hem rood maakt.
"""

from __future__ import annotations

import pytest

from src.core.api.auth.router_token import _mag_token_intrekken
from src.core.auth.api_deps import UserResponse, VerifiedJWTPayload

_TENANT = 7


def _aanvrager(*, user_id: int = 5, rollen: list[str] | None = None) -> UserResponse:
    return UserResponse(
        id=user_id, email="a@x.example", tenant_id=_TENANT, roles=rollen or [], is_active=True
    )


def _payload(**velden: object) -> VerifiedJWTPayload:
    basis: dict[str, object] = {"sub": "5", "tenant_id": _TENANT, "jti": "j", "exp": 9999999999}
    basis.update(velden)
    return basis  # type: ignore[return-value]  # TypedDict-vorm van een getekende claim


def test_the_owner_may_revoke_their_own_token() -> None:
    assert _mag_token_intrekken(_aanvrager(), _payload()) is True


def test_a_colleague_without_admin_role_may_not() -> None:
    assert _mag_token_intrekken(_aanvrager(), _payload(sub="6")) is False


def test_an_admin_of_the_same_tenant_may() -> None:
    assert _mag_token_intrekken(_aanvrager(rollen=["admin"]), _payload(sub="6")) is True


def test_an_admin_of_another_tenant_may_not() -> None:
    assert (
        _mag_token_intrekken(_aanvrager(rollen=["admin"]), _payload(sub="6", tenant_id=_TENANT + 1))
        is False
    )


def test_a_portal_token_with_the_same_number_is_not_mine() -> None:
    assert _mag_token_intrekken(_aanvrager(), _payload(aud="portal")) is False


def test_a_token_of_the_same_number_in_another_tenant_is_not_mine() -> None:
    assert _mag_token_intrekken(_aanvrager(), _payload(tenant_id=_TENANT + 1)) is False


@pytest.mark.parametrize("sub", ["abc", "", "5.0", None])
def test_a_sub_that_is_not_a_number_is_refused_without_an_exception(sub: object) -> None:
    assert _mag_token_intrekken(_aanvrager(rollen=["admin"]), _payload(sub=sub)) is False
