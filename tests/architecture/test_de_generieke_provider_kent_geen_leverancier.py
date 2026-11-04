"""De provider-agnostische laag bevat GEEN adres van een leverancier.

Besluit Rakesh 2026-09-20: de applicatie moet provider-agnostisch zijn en klanten geven hun
eigen eindpunt en sleutel op. `providers/openai_compatible.py` maakt dat waar: hij praat met
elk eindpunt dat het OpenAI-chatprotocol aanbiedt, en `base_url` komt van de aanroeper.

**Waarom dit een bewaker nodig heeft en niet alleen een afspraak.** De goedkoopste manier om
deze laag "handiger" te maken is een standaardadres invullen -- "want negen van de tien keer is
het toch die ene leverancier". Precies daarmee krijgt er weer een een voorkeurspositie in onze
code, en de volgende sessie bouwt erop voort. De lock-in verdwijnt dan niet, hij verhuist naar
een regeltje dat niemand meer ziet.

**Drie bestanden, en twee daarvan zijn na een reviewronde toegevoegd.** De eerste versie
keek alleen naar `openai_compatible.py` -- het bestand met vijftien regels docstring die
uitleggen waarom een adres daar niet mag. Dat is de deur waar niemand doorheen loopt. Ronde 2
voegde de FABRIEK toe (`base_url = base_url or "..."`), ronde 3 de gedeelde `LLMConfig` in
`base.py`, waar een default in een klap voor ELKE provider geldt. Elke ronde vond een deur
waar de vorige niet aan had gedacht; dat is het patroon uit
`valkuil_uitzonderingslijst_per_bestand_maakt_guard_blind` en de reden dat het bereik expliciet
in `BEWAAKT` staat in plaats van in proza.

**Wat deze bewaker NIET kan, en dat hoort hier te staan.** Hij leest stringliteralen uit de
AST. Een adres dat op runtime wordt samengesteld (`"https" + "://" + host`) ziet hij niet;
gemeten en bevestigd bij de review. Aangrenzende literalen (`"https:" "//x"`) worden door
Python bij het parsen samengevoegd en dus WEL gezien. Voor de faalvorm waar dit tegen bedoeld
is -- iemand vult een standaardadres in -- is dat genoeg; voor iemand die het bewust verstopt
niet, en daar is een bewaker sowieso het verkeerde gereedschap.

`#`-commentaar valt buiten het bereik: dat zijn geen literalen in de AST. Daar mag een adres
staan als toelichting.

Dit geldt ALLEEN voor de bestanden in `BEWAAKT`. `providers/deepseek.py`,
`providers/gemini.py` en `providers/ollama.py` zijn leverancier-specifieke klassen; daar hoort
hun eigen adres juist wel.

Mutatietest (2026-09-20, met scripts/mutation_harness.py):
1. Een standaardadres toegewezen in `_validate_config` -> ROOD, met dat adres in de melding.
2. Hetzelfde adres in een module-constante -> ROOD.
3. Hetzelfde adres IN de moduledocstring -> ROOD. Apart gedraaid, want richting 2 dekt hem
   niet: een constante is een gewoon literaal, een docstring is de eerste expressie van de
   module. Zonder deze meting zou de claim "de docstring telt mee" onbewezen zijn.
4. Een adres als terugval in `factory.py::create` -> ROOD (bereik toegevoegd na ronde 2).
5. Een default `base_url` op `LLMConfig` in `base.py` -> ROOD (bereik toegevoegd na ronde 3).
   Gemeten: `base.py` bevat vandaag geen enkel http-adres, dus de uitbreiding maakt niets rood
   dat al stond.
6. Ongewijzigd -> GROEN, en `test_de_bewaker_leest_echt_literalen` bewijst dat er literalen
   zijn gelezen; nul literalen zou richting 1 vanzelf groen maken.
"""

from __future__ import annotations

import ast
from pathlib import Path

_WORTEL = Path(__file__).resolve().parents[2] / "src" / "core" / "services" / "llm"

#: De laag die per definitie leverancier-onafhankelijk moet blijven.
BEWAAKT = {
    "providers/openai_compatible.py": "de generieke provider zelf",
    "factory.py": "de fabriek -- de natuurlijke plek voor een terugval-adres",
    # Toegevoegd na Gate 2, ronde 3. `LLMConfig` leeft hier, en een default op `base_url`
    # geeft ELKE provider zonder eigen adres in een klap een standaardleverancier. Dat is de
    # derde deur: de bewaker stond voor de twee waar je aan denkt.
    "base.py": "de gedeelde LLMConfig -- een default hier geldt voor alle providers",
}

_SCHEMAS = ("http://", "https://")


def _literalen(pad: Path) -> list[str]:
    boom = ast.parse(pad.read_text(encoding="utf-8"))
    return [
        knoop.value
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.Constant) and isinstance(knoop.value, str)
    ]


def test_de_bewaakte_bestanden_bestaan_nog() -> None:
    """Een verhuisd bestand zou de bewaker hieronder stil vacuum maken."""
    ontbreekt = [naam for naam in BEWAAKT if not (_WORTEL / naam).exists()]
    assert not ontbreekt, f"niet gevonden onder {_WORTEL}: {ontbreekt}"


def test_de_bewaker_leest_echt_literalen() -> None:
    """Nul literalen maakt de volgende test trivially groen."""
    for naam in BEWAAKT:
        assert len(_literalen(_WORTEL / naam)) > 5, f"{naam} leverde bijna geen literalen op"


def test_er_staat_geen_leveranciersadres_in_de_agnostische_laag() -> None:
    """Geen enkel stringliteraal in de bewaakte bestanden mag een absoluut http-adres zijn."""
    gevonden: dict[str, list[str]] = {}
    for naam in BEWAAKT:
        treffers = [
            tekst
            for tekst in _literalen(_WORTEL / naam)
            if any(schema in tekst for schema in _SCHEMAS)
        ]
        if treffers:
            gevonden[naam] = treffers

    assert not gevonden, (
        "De provider-agnostische laag mag GEEN adres van een leverancier bevatten -- dan "
        "krijgt er weer een een voorkeurspositie in onze code en verhuist de lock-in naar een "
        f"standaardwaarde. Gevonden: {gevonden}. Geef het adres mee via `base_url`."
    )
