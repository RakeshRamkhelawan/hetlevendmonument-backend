"""Wie `provider_name` overschrijft, moet ook `serves_mock` overschrijven.

**Waarom deze regel bestaat.** `LLMService` weigert in productie te starten als het taalmodel
een namaakmodel is. Die controle vroeg tot 2026-09-21 `provider_name == "mock"`, en die naam
wordt in de basisklasse afgeleid van de KLASSENAAM. Een samengestelde provider heet dan
"keten" en glipt erlangs, ook als hij intern alleen een namaakmodel bereikt. Sinds vandaag
vraagt de controle `serves_mock`.

Maar die eigenschap heeft een STANDAARD, en die standaard leidt het antwoord af uit dezelfde
naam. Daarmee is het gat verplaatst in plaats van gesloten: een klasse die `provider_name`
zelf bepaalt, bepaalt via de achterdeur ook `serves_mock` -- en een klasse die de standaard
erft terwijl zijn naam niets over zijn inhoud zegt, antwoordt fout.

Beide Gate 2-reviewers wezen dat aan, en een van hen mat het uit op een echt geval:
`OpenAICompatibleProvider` overschrijft `provider_name` met een label dat sinds BE-LLM-003 uit
een vrij tekstveld van de KLANT komt. Een klant die zijn eindpunt "mock" noemde, kreeg
`serves_mock=True` op een echt eindpunt.

**Deze bewaker maakt van die conventie een eis.** De regel is opzettelijk gekoppeld aan
`provider_name` en niet aan "houdt een lijst providers vast": de samengestelde provider van
fase 2b bestaat nog niet, en een bewaker schrijven voor een klasse die je nog moet bedenken,
deelt de blinde vlek van wie hem bedenkt. Wat je WEL kunt vastleggen is de eigenschap die het
risico veroorzaakt, en die is vandaag meetbaar: de naam komt niet uit de klasse.

Mutatietest (2026-09-21, met scripts/mutation_harness.py):
1. `serves_mock` uit `openai_compatible.py` gehaald -> ROOD.
2. `serves_mock` uit `mock.py` gehaald -> ROOD.
3. een nieuwe klasse met alleen `provider_name` toegevoegd -> ROOD.
4. ongewijzigd -> GROEN. `test_de_bewaker_vindt_de_providers` bewijst dat de verzameling niet
   leeg is; een lege verzameling zou de eis vanzelf groen maken.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

_WORTEL = Path(__file__).resolve().parents[2]

#: De basisklasse waarvan dit geldt. Bewust de volledige naam: `src/core/als/llm_integration/
#: providers.py` heeft eigen klassen die OOK `LLMProvider` heten maar een andere basis hebben
#: en `LLMService` nooit bereiken.
_BASIS = "LLMProvider"

#: De map waar de providers van DEZE stack wonen. `src/core/llm/` is de oude, parallelle stack
#: met een eigen `LLMService`; die valt buiten deze bewaker en heeft een eigen bevinding.
_PROVIDERMAP = "src/core/services/llm/providers"

_NAAM = "provider_name"
_MOCKVLAG = "serves_mock"


def _providerbestanden() -> list[Path]:
    """De getrackte EN ongetrackte bestanden in de providermap.

    `--untracked` is geen extraatje: `git grep` zoekt standaard alleen in getrackte bestanden,
    en een provider die vandaag wordt toegevoegd is precies het geval waarvoor deze bewaker
    bestaat (gemeten 2026-09-20 bij een andere bewaker: die vond nul schrijvers omdat het
    nieuwe bestand nog niet gecommit was).
    """
    uitvoer = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", _PROVIDERMAP],
        cwd=_WORTEL,
        capture_output=True,
        text=True,
        check=False,
    )
    return [
        _WORTEL / regel.strip()
        for regel in uitvoer.stdout.splitlines()
        if regel.strip().endswith(".py")
    ]


def _eigenschappen(klasse: ast.ClassDef) -> set[str]:
    """Namen van de properties en attributen die deze klasse ZELF definieert.

    Expliciet over de directe kinderen en NIET met `ast.walk()`: die duikt geneste functies in
    en zou een lokale variabele met dezelfde naam meetellen (valkuil
    `ast_walk_duikt_functiebodies_in`).
    """
    namen: set[str] = set()
    for knoop in klasse.body:
        if isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            namen.add(knoop.name)
        elif isinstance(knoop, ast.Assign):
            for doel in knoop.targets:
                if isinstance(doel, ast.Name):
                    namen.add(doel.id)
        elif isinstance(knoop, ast.AnnAssign) and isinstance(knoop.target, ast.Name):
            namen.add(knoop.target.id)
    return namen


def _providers() -> dict[str, set[str]]:
    """`bestand::klasse` -> de eigenschappen die die klasse zelf definieert."""
    gevonden: dict[str, set[str]] = {}
    for pad in _providerbestanden():
        boom = ast.parse(pad.read_text(encoding="utf-8"))
        relatief = pad.relative_to(_WORTEL).as_posix()
        for knoop in boom.body:
            if not isinstance(knoop, ast.ClassDef):
                continue
            basisnamen = {
                b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in knoop.bases
            }
            if _BASIS in basisnamen:
                gevonden[f"{relatief}::{knoop.name}"] = _eigenschappen(knoop)
    return gevonden


def test_de_bewaker_vindt_de_providers() -> None:
    """Nul providers zou de volgende test trivially groen maken."""
    assert _providers(), "geen enkele LLMProvider-subklasse gevonden -- de bewaker is leeg"


def test_wie_provider_name_overschrijft_overschrijft_ook_serves_mock() -> None:
    """De eis zelf.

    `provider_name` overschrijven betekent: de naam van deze provider komt NIET uit zijn
    klasse. En dan kan de standaard van `serves_mock`, die uit diezelfde naam wordt afgeleid,
    niet meer kloppen -- hij antwoordt dan op een tekst die iemand anders kiest.
    """
    zonder = sorted(
        sleutel
        for sleutel, eigen in _providers().items()
        if _NAAM in eigen and _MOCKVLAG not in eigen
    )

    assert not zonder, (
        f"Deze providers bepalen hun eigen `{_NAAM}` maar laten `{_MOCKVLAG}` aan de "
        f"standaard over: {zonder}. Die standaard leidt het antwoord af uit de naam, dus de "
        "productieguard in LLMService gaat dan af op een tekst in plaats van op wat deze "
        f"provider werkelijk bedient. Geef `{_MOCKVLAG}` expliciet een waarde, met de reden."
    )


def test_de_standaard_blijft_bestaan_voor_wie_zijn_naam_NIET_kiest() -> None:
    """De tegenrichting. Zonder deze helft is "elke provider moet alles overschrijven" een
    geldige oplossing, en dan is de standaard in de basisklasse dode code.

    De drie bladproviders die hun naam uit de klassenaam halen, horen `serves_mock` juist NIET
    te overschrijven: daar klopt de afleiding per constructie.
    """
    erfgenamen = [
        sleutel
        for sleutel, eigen in _providers().items()
        if _NAAM not in eigen and _MOCKVLAG not in eigen
    ]

    assert erfgenamen, (
        "geen enkele provider erft de standaard nog -- als dat klopt is de standaard in "
        "LLMProvider.serves_mock dode code en hoort hij weg, en anders is deze bewaker te "
        "streng geworden"
    )
