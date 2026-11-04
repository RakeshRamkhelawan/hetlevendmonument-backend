"""De ene definitie van "deze gebruiker is een platformbeheerder" (brief 2026-10-19).

De definitie is een zuivere functie: de vlag OF een platformrol, in elke schrijfwijze. De routes en de dienst
gebruiken alleen deze. De breedte-s wordt met chr() gebouwd (ASCII-only regel).
"""

from __future__ import annotations

import pytest

from src.core.services.rbac_service import telt_als_platformbeheerder


def test_alleen_de_vlag_is_genoeg() -> None:
    assert telt_als_platformbeheerder(True, ["admin"]) is True


def test_alleen_de_platformrol_is_genoeg() -> None:
    assert telt_als_platformbeheerder(False, ["system_admin"]) is True


@pytest.mark.parametrize(
    "naam",
    ["System_Admin", "SYSTEM_ADMIN", "  system_admin  ", chr(0xFF53) + "ystem_admin"],
)
def test_een_andere_schrijfwijze_van_de_platformrol_telt_ook(naam: str) -> None:
    assert telt_als_platformbeheerder(False, [naam]) is True


def test_zonder_vlag_en_zonder_platformrol_is_het_geen_platformbeheerder() -> None:
    assert telt_als_platformbeheerder(False, ["admin", "editor", "user"]) is False


def test_een_gebruiker_zonder_rollen_en_zonder_vlag_is_het_niet() -> None:
    assert telt_als_platformbeheerder(False, []) is False
