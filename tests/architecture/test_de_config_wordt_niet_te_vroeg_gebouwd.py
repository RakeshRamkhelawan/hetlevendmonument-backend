"""De testopstelling MOET merken dat de config al gebouwd is (ADR-036 OP-243).

**Wat hier is vervangen en waarom.** De eerste versie van deze guard
(`test_database_url_staat_voor_de_src_import.py`, 2026-09-15) toetste met een AST-parse of
de `DATABASE_URL`-toekenning BOVEN de `src.main`-import stond. Dat bewaakte de ene oorzaak
die we toen kenden. Elke andere import boven die regel die `config` aanraakt, bevriest de
configuratie net zo hard -- en die guard bleef daarbij groen. Rakesh wees daarop.

Nu wordt de TOESTAND bewaakt in plaats van de oorzaak:
`tests/fixtures/configvolgorde.py` controleert of `unified_config._config_instance` al
gevuld is op het moment dat de conftest de omgeving gaat zetten. Die vraag is in elke run te
stellen -- ook in een unittestrun zonder database -- en is onafhankelijk van WELKE import het
deed.

Dit bestand bewaakt dat die controle er is, werkt, en op de juiste plek wordt aangeroepen.
Zonder die laatste twee tests zou iemand de aanroep uit de conftest kunnen halen terwijl de
functie zijn eigen tests blijft halen -- een guard die alleen zichzelf bewijst.

**Mutatiebewijs (2026-09-15), beide richtingen:**
  1. Een module met een gevulde `_config_instance` -> de controle WERPT.
  2. Geen module / lege cache -> de controle laat door (anders zou "werp altijd" een
     geldige oplossing zijn en stond de hele suite stil).
  3. De aanroep uit `tests/conftest.py` verwijderd -> ROOD.
  4. De aanroep NA de `src.main`-import gezet -> ROOD.
"""

from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

from tests.fixtures.configvolgorde import (
    CACHE_ATTRIBUUT,
    CONFIG_MODULE,
    ConfigTeVroegGebouwd,
    controleer_config_nog_niet_gebouwd,
)

_CONFTEST = Path("tests/conftest.py")
_CONTROLE = "controleer_config_nog_niet_gebouwd"


def test_de_controle_werpt_als_de_config_al_gebouwd_is() -> None:
    """De richting die de fout vangt."""
    nep = types.ModuleType(CONFIG_MODULE)
    setattr(nep, CACHE_ATTRIBUUT, object())  # alsof get_config() al heeft gedraaid

    with pytest.raises(ConfigTeVroegGebouwd) as fout:
        controleer_config_nog_niet_gebouwd({CONFIG_MODULE: nep})

    melding = str(fout.value)
    assert "DATABASE_URL" in melding and "verplaats" in melding.lower(), (
        "De melding moet zeggen WAT er mis is en WAT je eraan doet; zonder dat zoekt de "
        f"volgende lezer zelf. Gekregen: {melding!r}"
    )


def test_de_controle_laat_de_normale_situatie_door() -> None:
    """De andere richting -- zonder deze zou 'werp altijd' een geldige oplossing zijn."""
    controleer_config_nog_niet_gebouwd({})  # module nog niet geimporteerd

    nep = types.ModuleType(CONFIG_MODULE)
    setattr(nep, CACHE_ATTRIBUUT, None)  # geimporteerd, nog niets gebouwd
    controleer_config_nog_niet_gebouwd({CONFIG_MODULE: nep})


def _boom() -> ast.Module:
    return ast.parse(_CONFTEST.read_text(encoding="utf-8"))


def _regel_van_aanroep(boom: ast.Module) -> int | None:
    for knoop in ast.walk(boom):
        if (
            isinstance(knoop, ast.Call)
            and isinstance(knoop.func, ast.Name)
            and knoop.func.id == _CONTROLE
        ):
            return knoop.lineno
    return None


def _regel_van_src_main_import(boom: ast.Module) -> int | None:
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.ImportFrom) and knoop.module == "src.main":
            return knoop.lineno
    return None


def test_de_conftest_roept_de_controle_daadwerkelijk_aan() -> None:
    """Een controle die nergens draait, bewaakt niets."""
    assert _regel_van_aanroep(_boom()) is not None, (
        f"`{_CONTROLE}(...)` wordt niet aangeroepen in {_CONFTEST}. De controle bestaat dan "
        "wel maar draait nergens -- precies de holle vorm uit quality-gates.md."
    )


def test_de_controle_staat_voor_de_src_main_import() -> None:
    """Na die import is het te laat: die bouwt de config."""
    boom = _boom()
    aanroep = _regel_van_aanroep(boom)
    import_regel = _regel_van_src_main_import(boom)

    assert aanroep is not None, "Zie de test hierboven."
    assert import_regel is not None, (
        f"Geen `from src.main import ...` gevonden in {_CONFTEST} -- deze guard toetst dan "
        "niets meer en moet worden bijgewerkt."
    )
    assert aanroep < import_regel, (
        f"De controle staat op regel {aanroep}, NA de src.main-import op regel "
        f"{import_regel}. Die import bouwt de config, dus de controle meet dan een "
        "toestand die hij zelf heeft veroorzaakt."
    )
