"""`has_role` en `can_manage_users` lezen rollen als TEKST (auth.UserResponse) en als OBJECT met `.name`.

De ingelogde gebruiker is een `UserResponse` met `roles: list[str]`; een ORM-gebruiker heeft
Role-objecten. Beide vormen tellen, hoofdletterongevoelig zoals `is_admin`. De hoofdletterongevoeligheid
is bedoeld gedrag: de gezaaide standaardrol heet `Admin`.

Producent: de tekstvorm gaat over de ECHTE `UserResponse`, niet over een eigen namaak.

Mutatiebewijs (kopie van shared.py): `has_role` altijd True -> de weigertests gaan ROOD; altijd False
-> de beheerderstests gaan ROOD. Geen autouse-fixture in tests/conftest.py raakt `has_role`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.api.v1.users.shared import can_manage_users, has_role
from src.core.auth.auth_service import UserResponse

_EIGEN = 2
_ANDERE = 1


def _tekst_gebruiker(roles: list[str], *, superuser: bool = False) -> UserResponse:
    return UserResponse(
        id=1, email="a@example.com", tenant_id=_EIGEN, roles=roles, is_superuser=superuser
    )


def _object_gebruiker(namen: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        tenant_id=_EIGEN,
        is_superuser=False,
        roles=[SimpleNamespace(name=n) for n in namen],
    )


@pytest.mark.parametrize("rol", ["admin", "Admin", "ADMIN", " admin "])
def test_has_role_matches_a_text_role_regardless_of_case(rol: str) -> None:
    assert has_role(_tekst_gebruiker([rol]), "admin") is True


@pytest.mark.parametrize("rol", ["admin", "Admin", "ADMIN"])
def test_has_role_matches_an_object_role_regardless_of_case(rol: str) -> None:
    assert has_role(_object_gebruiker([rol]), "admin") is True


def test_has_role_refuses_a_text_role_with_another_name() -> None:
    assert has_role(_tekst_gebruiker(["user"]), "admin") is False


def test_has_role_refuses_an_object_role_with_another_name() -> None:
    assert has_role(_object_gebruiker(["user"]), "admin") is False


def test_has_role_refuses_a_user_without_roles() -> None:
    assert has_role(_tekst_gebruiker([]), "admin") is False


def test_has_role_refuses_an_object_without_a_roles_attribute() -> None:
    assert has_role(SimpleNamespace(id=1), "admin") is False


def test_has_role_refuses_a_role_object_without_a_name() -> None:
    assert has_role(SimpleNamespace(roles=[SimpleNamespace()]), "admin") is False


def test_has_role_does_not_match_a_part_of_a_role_name() -> None:
    assert has_role(_tekst_gebruiker(["administrator"]), "admin") is False


@pytest.mark.parametrize("rol", ["admin", "Admin", "TenantAdmin", "tenantadmin"])
def test_can_manage_users_accepts_a_text_admin_in_the_own_tenant(rol: str) -> None:
    assert can_manage_users(_tekst_gebruiker([rol]), _EIGEN) is True


@pytest.mark.parametrize("rol", ["admin", "TenantAdmin"])
def test_can_manage_users_accepts_an_object_admin_in_the_own_tenant(rol: str) -> None:
    assert can_manage_users(_object_gebruiker([rol]), _EIGEN) is True


@pytest.mark.parametrize("namen", [["user"], []])
def test_can_manage_users_refuses_a_regular_text_user_in_the_own_tenant(
    namen: list[str],
) -> None:
    assert can_manage_users(_tekst_gebruiker(namen), _EIGEN) is False


@pytest.mark.parametrize("namen", [["user"], []])
def test_can_manage_users_refuses_a_regular_object_user_in_the_own_tenant(
    namen: list[str],
) -> None:
    assert can_manage_users(_object_gebruiker(namen), _EIGEN) is False


def test_can_manage_users_refuses_an_admin_of_another_tenant() -> None:
    assert can_manage_users(_tekst_gebruiker(["admin"]), _ANDERE) is False


def test_can_manage_users_lets_a_platform_superuser_cross_the_tenant_border() -> None:
    assert can_manage_users(_tekst_gebruiker([], superuser=True), _ANDERE) is True
