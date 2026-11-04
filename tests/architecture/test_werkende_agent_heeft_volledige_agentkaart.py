"""Elke agent die echt kan draaien heeft een volledige agentkaart (agentkaart dag 1, besluit Rakesh 2026-10-24).

Rakesh: "om een goed werkend agentic systeem te creeren zijn cruciale onderdelen nodig, data, prompt, koppelingen, dus een
rolbeschrijving is een hele cruciale onderdeel." Een agent werkt pas als tien dingen vastliggen: rol, regels van de klant,
gegevens, koppelingen, gereedschap, wanneer hij start, wat hij onthoudt, hoe hij uitlegt, hoe goed hij is (proefset) en wie
verantwoordelijk is. Rol, doel en gereedschap staan al in het skillmanifest (`role`, `goal`, `system_prompt`,
`allowed_tools`); de rest staat in het blok `agentkaart` van datzelfde manifest.

Welke agents: de bedrade agents (`_PILOT_WIRED_AGENT_IDS` in `src/core/als/enterprise/packs.py`; op de tak met agentstap heet dezelfde lijst ook `UITVOERBARE_AGENT_SLEUTELS`). De overige manifesten
hoeven nog geen kaart te hebben; een nieuwe agent wordt pas bedraad als zijn kaart er is.

Per veld wat telt als "ingevuld":
- `klantregels`: een niet-lege lijst van `{naam, standaard, betekenis, status}`, status `bestaat` of `gepland`;
- `gegevens`: een mapping met niet-lege `leest` en `schrijft`, elk element een niet-lege tekst;
- `koppelingen`: een lijst; LEEG mag deze dag (de sleutel moet er wel staan); elke koppeling heeft `{naam, doel, status}`;
- `start`: een mapping met `soort` (gebeurtenis, schema of handmatig) en een `naam`;
- `onthoudt`: een niet-lege lijst van `{wat, bron}` ("niets" is een geldig antwoord, maar dan staat het er);
- `waarom`: niet-lege tekst: wat de goedkeurder bij elk voorstel te zien krijgt;
- `proefset`: een mapping met `pad` en `drempel`; `todo` mag deze dag (dag 2 vult);
- `eigenaar`: niet-lege tekst: de rol die verantwoordelijk is (de koppeling aan een persoon is ADR-039 F5);
- `vakregels`: minstens drie regels in gewone taal, elk beginnend met Altijd, Nooit of Stopt.

**Mutatiebewijs (2026-10-24), een regel per veld:** zie `TestElkVeldWordtAfgedwongen` (synthetisch, per veld weghalen en
leegmaken) en de eindmelding van de sessie (op het echte debiteurenmanifest). Legitiem: een niet-bedrade agent zonder kaart
blijft groen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORTEL = Path(__file__).resolve().parents[2]
MANIFESTEN = WORTEL / "src" / "core" / "als" / "agents" / "skills" / "manifests"

VELDEN = (
    "klantregels",
    "gegevens",
    "koppelingen",
    "start",
    "onthoudt",
    "waarom",
    "proefset",
    "eigenaar",
    "vakregels",
)
START_SOORTEN = frozenset({"gebeurtenis", "schema", "handmatig"})
STATUSSEN = frozenset({"bestaat", "gepland"})
VAKREGEL_BEGINNEN = ("Altijd", "Nooit", "Stopt")


def _tekst(waarde: object) -> bool:
    return isinstance(waarde, str) and bool(waarde.strip())


def _gevuld(waarde: object) -> bool:
    """Een ingevulde waarde: een tekst telt alleen als er iets anders dan spaties in staat; een getal of lijst als hij niet leeg is."""
    if isinstance(waarde, str):
        return bool(waarde.strip())
    if isinstance(waarde, (list, dict)):
        return bool(waarde)
    return isinstance(waarde, (int, float)) and not isinstance(waarde, bool)


def _items(waarde: object, sleutels: tuple[str, ...]) -> bool:
    """Een niet-lege lijst van mappings waarin elke genoemde sleutel een niet-lege waarde heeft."""
    if not isinstance(waarde, list) or not waarde:
        return False
    return all(
        isinstance(item, dict) and all(_gevuld(item.get(s)) for s in sleutels)
        for item in waarde
    )


def _gebrek_klantregels(kaart: dict[str, Any]) -> str | None:
    regels = kaart["klantregels"]
    if _items(regels, ("naam", "standaard", "betekenis", "status")) and all(
        isinstance(item["status"], str) and item["status"] in STATUSSEN for item in regels
    ):
        return None
    return "klantregels: een lijst van {naam, standaard, betekenis, status (bestaat of gepland)} is nodig en mag niet leeg zijn"


def _gebrek_gegevens(kaart: dict[str, Any]) -> str | None:
    gegevens = kaart["gegevens"]
    if isinstance(gegevens, dict) and all(
        isinstance(gegevens.get(zijde), list)
        and gegevens[zijde]
        and all(_tekst(x) for x in gegevens[zijde])
        for zijde in ("leest", "schrijft")
    ):
        return None
    return "gegevens: een mapping met niet-lege `leest` en `schrijft` is nodig, elk element een niet-lege tekst"


def _gebrek_koppelingen(kaart: dict[str, Any]) -> str | None:
    koppelingen = kaart["koppelingen"]
    if isinstance(koppelingen, list) and (not koppelingen or _items(koppelingen, ("naam", "doel", "status"))):
        return None
    return "koppelingen: een lijst is nodig (leeg mag); elke koppeling heeft {naam, doel, status}"


def _gebrek_start(kaart: dict[str, Any]) -> str | None:
    start = kaart["start"]
    if (
        isinstance(start, dict)
        and isinstance(start.get("soort"), str)
        and start["soort"] in START_SOORTEN
        and _tekst(start.get("naam"))
    ):
        return None
    return "start: een mapping met `soort` (gebeurtenis, schema, handmatig) en een `naam` is nodig"


def _gebrek_proefset(kaart: dict[str, Any]) -> str | None:
    proefset = kaart["proefset"]
    if isinstance(proefset, dict) and _tekst(proefset.get("pad")) and proefset.get("drempel") not in (None, ""):
        return None
    return "proefset: een mapping met `pad` en `drempel` is nodig (`todo` mag)"


def _gebrek_vakregels(kaart: dict[str, Any]) -> str | None:
    vakregels = kaart["vakregels"]
    if (
        isinstance(vakregels, list)
        and len(vakregels) >= 3
        and all(_tekst(r) and r.startswith(VAKREGEL_BEGINNEN) for r in vakregels)
    ):
        return None
    return "vakregels: minstens drie regels in gewone taal zijn nodig, elk beginnend met Altijd, Nooit of Stopt"


def _gebrek_tekst(kaart: dict[str, Any], veld: str, uitleg: str) -> str | None:
    return None if _tekst(kaart[veld]) else f"{veld}: {uitleg}"


def _gebrek_onthoudt(kaart: dict[str, Any]) -> str | None:
    if _items(kaart["onthoudt"], ("wat", "bron")):
        return None
    return "onthoudt: een niet-lege lijst van {wat, bron} is nodig"


def kaart_gebreken(kaart: object) -> list[str]:
    """De gebreken van een agentkaart, per veld; een lege lijst is een volledige kaart."""
    if not isinstance(kaart, dict):
        return ["geen blok `agentkaart`"]
    ontbrekend = [f"{veld}: ontbreekt" for veld in VELDEN if veld not in kaart]
    if ontbrekend:
        return ontbrekend
    gevonden = [
        _gebrek_klantregels(kaart),
        _gebrek_gegevens(kaart),
        _gebrek_koppelingen(kaart),
        _gebrek_start(kaart),
        _gebrek_onthoudt(kaart),
        _gebrek_tekst(kaart, "waarom", "niet-lege tekst is nodig"),
        _gebrek_proefset(kaart),
        _gebrek_tekst(kaart, "eigenaar", "niet-lege tekst is nodig"),
        _gebrek_vakregels(kaart),
    ]
    return [gebrek for gebrek in gevonden if gebrek is not None]


def _bedrade_agents() -> frozenset[str]:
    from src.core.als.enterprise.packs import _PILOT_WIRED_AGENT_IDS

    return _PILOT_WIRED_AGENT_IDS


def _manifest(sleutel: str) -> dict[str, Any]:
    pad = MANIFESTEN / f"{sleutel}.yml"
    assert pad.is_file(), f"de bedrade agent {sleutel} heeft geen manifest op {pad}"
    data = yaml.safe_load(pad.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.mark.parametrize(
    "sleutel", sorted(["crediteuren", "dunning", "receiptscanner", "skillsgaptraining", "vatcompliance"])
)
def test_elke_bedrade_agent_heeft_een_volledige_agentkaart(sleutel: str) -> None:
    assert sleutel in _bedrade_agents(), f"{sleutel} is niet meer bedraad; haal hem uit deze lijst"

    gebreken = kaart_gebreken(_manifest(sleutel).get("agentkaart"))

    assert gebreken == [], f"{sleutel}: de agentkaart is niet volledig:\n  " + "\n  ".join(gebreken)


def test_de_lijst_van_deze_test_is_de_lijst_van_bedrade_agents() -> None:
    """Een nieuw bedrade agent moet hier meedoen: zonder deze toets kan hij zonder kaart langs komen."""
    assert _bedrade_agents() == {
        "crediteuren",
        "dunning",
        "receiptscanner",
        "skillsgaptraining",
        "vatcompliance",
    }


def test_een_niet_bedrade_agent_zonder_kaart_is_geen_gebrek() -> None:
    """De andere kant: de 131 niet-bedrade manifesten hoeven nog geen kaart (en deze test eist hem ook niet)."""
    niet_bedraad = "technicalwriter"
    assert niet_bedraad not in _bedrade_agents()
    assert "agentkaart" not in _manifest(niet_bedraad)


GOEDE_KAART: dict[str, Any] = {
    "klantregels": [{"naam": "a", "standaard": 14, "betekenis": "b", "status": "bestaat"}],
    "gegevens": {"leest": ["x"], "schrijft": ["y"]},
    "koppelingen": [],
    "start": {"soort": "handmatig", "naam": "scherm"},
    "onthoudt": [{"wat": "w", "bron": "b"}],
    "waarom": "omdat",
    "proefset": {"pad": "todo", "drempel": "todo"},
    "eigenaar": "debiteurenbeheerder",
    "vakregels": ["Altijd: een", "Nooit: twee", "Stopt: drie"],
}


class TestElkVeldWordtAfgedwongen:
    """Mutatiebewijs: een goede kaart heeft geen gebreken; per veld weghalen of leegmaken geeft een gebrek."""

    def test_een_goede_kaart_heeft_geen_gebreken(self) -> None:
        assert kaart_gebreken(GOEDE_KAART) == []

    @pytest.mark.parametrize("veld", VELDEN)
    def test_een_ontbrekend_veld_wordt_gevonden(self, veld: str) -> None:
        kaart = {k: v for k, v in GOEDE_KAART.items() if k != veld}

        assert any(g.startswith(f"{veld}:") for g in kaart_gebreken(kaart))

    @pytest.mark.parametrize(
        ("veld", "leeg"),
        [
            ("klantregels", []),
            ("gegevens", {"leest": [], "schrijft": ["y"]}),
            ("start", {"soort": "nooit", "naam": "x"}),
            ("onthoudt", []),
            ("waarom", "  "),
            ("proefset", {"pad": "", "drempel": 0.8}),
            ("eigenaar", ""),
            ("vakregels", ["Altijd: een", "Nooit: twee"]),
            ("vakregels", ["een", "twee", "drie"]),
            ("klantregels", [{"naam": "a", "standaard": 14, "betekenis": "b"}]),
            ("klantregels", [{"naam": "a", "standaard": 14, "betekenis": "b", "status": "misschien"}]),
            ("gegevens", {"leest": ["x", " "], "schrijft": ["y"]}),
            ("koppelingen", [{"naam": "mail"}]),
            ("koppelingen", [{"naam": " ", "doel": "x", "status": "bestaat"}]),
            ("klantregels", [{"naam": "a", "standaard": 14, "betekenis": "b", "status": ["bestaat"]}]),
            ("start", {"soort": ["handmatig"], "naam": "x"}),
        ],
    )
    def test_een_leeg_veld_wordt_gevonden(self, veld: str, leeg: object) -> None:
        kaart = {**GOEDE_KAART, veld: leeg}

        assert any(g.startswith(f"{veld}:") for g in kaart_gebreken(kaart))

    def test_koppelingen_mag_leeg_zijn_maar_moet_een_lijst_zijn(self) -> None:
        assert kaart_gebreken({**GOEDE_KAART, "koppelingen": []}) == []
        assert any(
            g.startswith("koppelingen:")
            for g in kaart_gebreken({**GOEDE_KAART, "koppelingen": "mail"})
        )

    def test_proefset_mag_todo_zijn_deze_dag(self) -> None:
        assert kaart_gebreken({**GOEDE_KAART, "proefset": {"pad": "todo", "drempel": "todo"}}) == []

    def test_een_manifest_zonder_blok_geeft_een_gebrek(self) -> None:
        assert kaart_gebreken(None) == ["geen blok `agentkaart`"]
