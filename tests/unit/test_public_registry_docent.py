"""Welke paden van de docentenomgeving de TenantMiddleware zonder JWT doorlaat (BE-EP-055).

Gemeten 2026-11-03 op productie: PUT /edu/antwoorden/7 gaf 401 "Missing or invalid
authentication" van de TenantMiddleware, terwijl de route zelf de klassessie (cookie) eist.
De unittests van de routes riepen de functies direct aan en zagen de middleware niet.
"""

from __future__ import annotations

import pytest

from src.core.shared.public_registry import PublicEndpointRegistry

pytestmark = [pytest.mark.unit]

_BASIS = "/api/v1/hetlevendmonument/foundation"


@pytest.mark.parametrize("sub", ["/edu/antwoorden/7", "/docent/aanvraag"])
def test_leerlingantwoorden_en_aanvraag_zijn_zonder_jwt_bereikbaar(sub: str) -> None:
    assert PublicEndpointRegistry.is_public(_BASIS + sub)
    assert PublicEndpointRegistry.is_public("/hetlevendmonument/foundation" + sub)


@pytest.mark.parametrize(
    "sub",
    [
        "/docent/klassen",
        "/docent/klassen/8/antwoorden",
        "/docent/ik",
        "/docent/lesmateriaal/7/pdf",
        "/admin/docenten/aanvragen",
        "/edu/antwoordenx",
        "/docent/aanvraagx",
    ],
)
def test_de_rest_van_de_docentenomgeving_eist_een_jwt(sub: str) -> None:
    assert not PublicEndpointRegistry.is_public(_BASIS + sub)
