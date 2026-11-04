"""Elk pakket in de catalogus heeft een Nederlandse weergavenaam (zero-admin afwerken, 2026-10-19).

Acceptatie: alle pakketnamen waren Engels ("Zero-Admin Bookkeeping", "Employee Reskilling & Mobility"). De catalogus
(`config/domain_packs.yaml`) is de ENE bron: elk pakket krijgt daar een `display_name` (Nederlands, alleen ASCII zoals
de rest van de schermtekst); de pilootpakketten krijgen ook een korte `description`. De technische `pack_id` en de
Engelse `name` blijven zoals ze waren; de packs-API geeft de weergavenaam erbij en het scherm toont die.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from src.core.api.v1.packs.dependencies import CataloguePack, get_pack_catalogue
from src.core.api.v1.packs.router import _pakket

CATALOGUS = Path(__file__).resolve().parents[3] / "config" / "domain_packs.yaml"
PILOOT = ("mkb.zero_admin", "hr.reskilling_engine")


def _pakketten() -> list[dict[str, object]]:
    return yaml.safe_load(CATALOGUS.read_text(encoding="utf-8"))["packs"]


class TestElkPakketHeeftEenNederlandseNaam:
    def test_every_pack_has_a_display_name(self) -> None:
        zonder = [p["pack_id"] for p in _pakketten() if not str(p.get("display_name", "")).strip()]

        assert zonder == []

    def test_no_display_name_is_the_english_name(self) -> None:
        gelijk = [p["pack_id"] for p in _pakketten() if p.get("display_name") == p["name"]]

        assert gelijk == []

    def test_display_names_are_unique(self) -> None:
        namen = [p.get("display_name") for p in _pakketten()]

        assert len(namen) == len(set(namen))

    def test_display_names_are_plain_ascii(self) -> None:
        niet_ascii = [
            p["pack_id"] for p in _pakketten() if not str(p.get("display_name", "")).isascii()
        ]

        assert niet_ascii == []

    def test_a_display_name_is_short_enough_for_a_list(self) -> None:
        te_lang = [p["pack_id"] for p in _pakketten() if len(str(p.get("display_name", ""))) > 60]

        assert te_lang == []

    def test_the_technical_pack_id_is_untouched(self) -> None:
        ongeldig = [
            p["pack_id"]
            for p in _pakketten()
            if not re.fullmatch(r"[a-z]+\.[a-z0-9_]+", str(p["pack_id"]))
        ]

        assert ongeldig == []

    def test_the_english_name_is_still_there(self) -> None:
        assert all(str(p.get("name", "")).strip() for p in _pakketten())

    @pytest.mark.parametrize("pack_id", PILOOT)
    def test_a_pilot_pack_has_a_dutch_description(self, pack_id: str) -> None:
        pakket = next(p for p in _pakketten() if p["pack_id"] == pack_id)

        beschrijving = str(pakket.get("description", ""))

        assert len(beschrijving) >= 20 and beschrijving.isascii()

    def test_the_zero_admin_pack_has_the_expected_name(self) -> None:
        pakket = next(p for p in _pakketten() if p["pack_id"] == "mkb.zero_admin")

        assert pakket.get("display_name") == "Boekhouding zonder gedoe"


class TestDeCatalogusGeeftDeNaamDoor:
    def test_the_loaded_catalogue_has_the_display_name(self) -> None:
        pakketten = get_pack_catalogue()

        assert pakketten["mkb.zero_admin"].display_name == "Boekhouding zonder gedoe"

    def test_the_loaded_catalogue_has_the_description_of_a_pilot_pack(self) -> None:
        assert get_pack_catalogue()["mkb.zero_admin"].description

    def test_every_loaded_pack_has_a_display_name(self) -> None:
        zonder = [i for i, p in get_pack_catalogue().items() if not p.display_name]

        assert zonder == []

    def test_the_english_name_stays_in_the_catalogue(self) -> None:
        assert get_pack_catalogue()["mkb.zero_admin"].name == "Zero-Admin Bookkeeping"

    def test_the_activation_row_carries_the_display_name(self) -> None:
        pakket = CataloguePack(
            pack_id="x.y", name="Engels", description=None, display_name="Nederlands"
        )

        rij = _pakket(pakket, None, met_wijziger=False)

        assert (rij["name"], rij["display_name"]) == ("Engels", "Nederlands")

    def test_a_pack_without_a_display_name_falls_back_to_the_name(self) -> None:
        pakket = CataloguePack(pack_id="x.y", name="Engels", description=None)

        rij = _pakket(pakket, None, met_wijziger=False)

        assert rij["display_name"] == "Engels"
