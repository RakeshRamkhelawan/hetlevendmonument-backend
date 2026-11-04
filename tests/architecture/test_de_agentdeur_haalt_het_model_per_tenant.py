"""De agent praat met het taalmodel van ZIJN tenant, niet met dat van het platform.

**Wat hier misging tot BE-LLM-004 (2026-09-23).** Fase 2a gaf een klant de mogelijkheid zijn
eigen LLM-eindpunt en sleutel te laten inrichten. `BaseSpecialistAgent._get_llm_service()`
bouwde ondertussen `LLMService()` -- de platformstandaard -- terwijl `self.tenant_id` gewoon
bekend was. De keten van de klant had nul aanroepers: opslag zonder gebruiker.

Zo'n gat komt niet terug met een testfout maar met een STILLE terugval, want beide paden
leveren een werkend taalmodel op. Alleen de rekening en de gegevensstroom verschillen, en die
ziet niemand in een testuitslag.

**Waarom op de AST en niet op tekst.** `"for_tenant" in bron` is groen zodra het woord ergens
staat -- in een comment, in een docstring, of in een regel die nooit wordt uitgevoerd. Dat is
de faalvorm die `quality-gates.md` elf keer optekent. Hier wordt de AANROEP gezocht: een
`ast.Call` naar `for_tenant` BINNEN de methode, met `self.tenant_id` als argument.

**Bijgewerkt 2026-09-24 (BE-LLM-005):** `for_tenant` neemt geen `db` meer mee -- hij opent zijn
eigen, korte sessie en sluit die voordat de adrescontrole begint. De asserties hieronder kloppen
onveranderd; het mutatierecept noemde een handtekening die niet meer bestaat.

**Mutatiebewijs (2026-09-23), beide richtingen:**

- `LLMService.for_tenant(self.tenant_id)` -> `LLMService()`: ROOD.
- `for_tenant(self.tenant_id)` -> `for_tenant(1)`: ROOD (een vaste tenant is precies
  de fout die dit moet vangen, en de naam `for_tenant` blijft dan staan).
- De terugval `self.llm = LLMService()` in het `except`-blok laten staan: GROEN voor DEZE guard.
  Sinds 2026-10-19 (Mistral-brief, ADR-041 B14) hoort die terugval er NIET meer te zijn: het
  platformmodel is in de uitrol DeepSeek. `tests/unit/llm/test_tenant_llm_keuze.py` bewaakt dat.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Het bestand en de methode waar de resolutie hoort te gebeuren. Expliciet genoemd zodat het
#: mutatiebewijs een regel per element kan hebben.
DEUR = ("src/core/als/agents/specialist_base.py", "_get_llm_service")


def _methode(pad: str, naam: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    boom = ast.parse((REPO_ROOT / pad).read_text(encoding="utf-8"))
    for knoop in ast.walk(boom):
        if isinstance(knoop, (ast.AsyncFunctionDef, ast.FunctionDef)) and knoop.name == naam:
            return knoop
    raise AssertionError(f"{naam} bestaat niet meer in {pad} -- is hij hernoemd?")


def _aanroepen(knoop: ast.AST, attribuut: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(knoop)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == attribuut
    ]


def test_de_agentdeur_vraagt_het_model_voor_zijn_eigen_tenant() -> None:
    pad, naam = DEUR
    methode = _methode(pad, naam)

    aanroepen = _aanroepen(methode, "for_tenant")
    assert aanroepen, (
        f"{pad}::{naam} roept `for_tenant` niet aan. Zonder die aanroep draait elke agent op "
        "het platformmodel en is de providerketen van de klant opslag zonder gebruiker."
    )

    met_eigen_tenant = [
        c
        for c in aanroepen
        if any(
            isinstance(a, ast.Attribute)
            and a.attr == "tenant_id"
            and isinstance(a.value, ast.Name)
            and a.value.id == "self"
            for a in c.args
        )
    ]
    assert met_eigen_tenant, (
        f"{pad}::{naam} roept `for_tenant` aan zonder `self.tenant_id` mee te geven. Een vaste "
        "of ontbrekende tenant levert de keten van de VERKEERDE klant op -- of die van niemand."
    )


def test_de_methode_is_async_want_de_keten_komt_uit_de_database() -> None:
    """Een synchrone versie kan de keten niet ophalen en zou stil terugvallen.

    Deze tweede assertie staat er omdat de eerste hem niet dekt: je kunt `for_tenant` aanroepen
    en het resultaat weggooien. `async def` is het goedkoopste structurele bewijs dat de
    resolutie werkelijk wordt afgewacht.
    """
    pad, naam = DEUR
    methode = _methode(pad, naam)

    assert isinstance(methode, ast.AsyncFunctionDef), (
        f"{pad}::{naam} is niet async. De providerketen staat in de database; een synchrone "
        "versie kan hem niet ophalen en valt dus altijd terug op het platformmodel."
    )
