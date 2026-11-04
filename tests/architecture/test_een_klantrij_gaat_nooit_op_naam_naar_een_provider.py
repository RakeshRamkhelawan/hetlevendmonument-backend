"""Hoe een klant zijn eindpunt NOEMT, mag nooit bepalen met welke klasse we praten.

**De faalvorm, gemeten op 2026-09-23.** `ProviderFactory.create()` kiest op NAAM: staat de naam
in de registry, dan komt de specifieke klasse. `configureer()` valideert de naam van een
klantrij niet -- het is een vrij tekstveld. Gevolg als `for_tenant` die naam aan `create()` zou
geven:

    rij heet "mock"   -> MockProvider; in productie een harde fout op onze eigen guard,
                         daarbuiten plausibele verzonnen tekst uit een namaakmodel
    rij heet "gemini" -> de Google-klasse, met het ADRES van de klant genegeerd en zijn
                         sleutel op weg naar een leverancier die hij niet koos

Dit is dezelfde fout als de productieguard van 2026-09-21, die `provider_name == "mock"`
toetste terwijl die naam uit de klassenaam kwam: beslissen op hoe iets HEET in plaats van op
wat het DOET. Een klant die zijn rij "mock" noemde, legde daarmee zijn eigen productie-LLM stil.

**Wat deze bewaker eist.** `LLMService.for_tenant` bouwt uitsluitend via
`ProviderFactory.create_generic`, waar de naam alleen een etiket is. Het gedragsbewijs staat in
`tests/unit/llm/test_het_verzoek_gaat_naar_het_gevalideerde_ip.py` en in de meting die bij deze
wijziging hoort: een rij met de naam "mock" levert `serves_mock=False` op.

**Mutatiebewijs (2026-09-23), beide richtingen:**

- `create_generic(rij.naam, ...)` -> `create(rij.naam, ...)`: ROOD op beide asserties.
- `create_generic(...)` helemaal weghalen: ROOD op de eerste.
- `ProviderFactory.create(...)` elders in `service.py` laten staan (de platformterugval via
  `__init__` gebruikt hem legitiem): GROEN -- deze bewaker kijkt alleen IN `for_tenant`.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DIENST = "src/core/services/llm/service.py"
METHODE = "for_tenant"

#: De fabrieksmethode die op NAAM kiest. Binnen `for_tenant` mag hij niet voorkomen.
OP_NAAM = "create"
#: De fabrieksmethode die de klasse vastlegt en de naam als etiket gebruikt.
GENERIEK = "create_generic"


def _methode() -> ast.AsyncFunctionDef | ast.FunctionDef:
    boom = ast.parse((REPO_ROOT / DIENST).read_text(encoding="utf-8"))
    for knoop in ast.walk(boom):
        if isinstance(knoop, (ast.AsyncFunctionDef, ast.FunctionDef)) and knoop.name == METHODE:
            return knoop
    raise AssertionError(f"{METHODE} bestaat niet meer in {DIENST} -- is hij hernoemd?")


def _aangeroepen_attributen(knoop: ast.AST) -> set[str]:
    return {
        n.func.attr
        for n in ast.walk(knoop)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }


def test_de_klantrij_gaat_door_de_generieke_fabriek() -> None:
    attributen = _aangeroepen_attributen(_methode())

    assert GENERIEK in attributen, (
        f"{DIENST}::{METHODE} bouwt zijn provider niet met `{GENERIEK}`. Alleen die weg legt de "
        "klasse vast; elke andere laat de KLANT bepalen met welke provider wij praten."
    )


def test_de_naam_van_de_klant_kiest_geen_klasse() -> None:
    attributen = _aangeroepen_attributen(_methode())

    assert OP_NAAM not in attributen, (
        f"{DIENST}::{METHODE} roept `ProviderFactory.{OP_NAAM}` aan. Die kiest op NAAM, en de "
        "naam van een klantrij is een vrij tekstveld: 'mock' levert een namaakmodel op, "
        "'gemini' de Google-klasse met het adres van de klant genegeerd."
    )
