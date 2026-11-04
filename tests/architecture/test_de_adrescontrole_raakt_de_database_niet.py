"""De tweede helft van de providerketen doet geen databasewerk (BE-LLM-005).

**Waarom deze bewaker bestaat.** `TenantLLMProviderService` is in fase 3 in twee helften
gesplitst: `opgeslagen_rijen()` haalt de rijen op (databasewerk) en `beproef()` controleert de
adressen en ontsleutelt de sleutels (netwerkwerk, tot vijf seconden naamsopzoeking per rij).
`LLMService.for_tenant` sluit de databasesessie TUSSEN die twee, omdat een agenttaak anders een
verbinding bezet houdt voor de duur van alle opzoekingen -- met vier rijen twintig seconden, op
een database die op 40 van de 50 verbindingen zit.

**Wat de bestaande test wel en niet dekt.** `test_de_sessie_is_DICHT_voordat_de_adrescontrole
_begint` legt de VOLGORDE vast. Wat hij niet kan zien, is wat een Gate 2-reviewer aanwees: het
dienstobject houdt die gesloten sessie nog vast, en `AsyncSession.close()` maakt een sessie niet
onbruikbaar -- hij begint stil een nieuwe transactie. De eerste databaseaanroep die iemand later
aan `beproef()` toevoegt, checkt dus een verbinding uit die niemand meer teruggeeft: precies de
schade die deze knip moest wegnemen, en zonder foutmelding.

Daarom deze structurele eis: in `beproef` komt `self._repo` niet voor. Dat is de regel die de
splitsing betekenis geeft, en hij is in vijf seconden te controleren.

**Mutatiebewijs (2026-09-24), beide richtingen:**

- een regel `await self._repo.actieve(tenant_id)` aan `beproef` toevoegen: ROOD.
- `self._repo` in `opgeslagen_rijen` en `configureer` laten staan: GROEN -- daar hoort het,
  die methodes DOEN databasewerk.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DIENST = "src/core/services/tenant_llm_provider_service.py"

#: De methode die na het sluiten van de sessie draait, en de methodes die er juist WEL
#: databasewerk in mogen doen. Expliciet genoemd zodat het mutatiebewijs een regel per element
#: kan hebben.
ZONDER_DATABASE = ("beproef",)
MET_DATABASE = ("opgeslagen_rijen", "configureer", "toon")


def _methode(naam: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    boom = ast.parse((REPO_ROOT / DIENST).read_text(encoding="utf-8"))
    for knoop in ast.walk(boom):
        if isinstance(knoop, (ast.AsyncFunctionDef, ast.FunctionDef)) and knoop.name == naam:
            return knoop
    raise AssertionError(f"{naam} bestaat niet meer in {DIENST} -- is hij hernoemd?")


def _raakt_de_repository(knoop: ast.AST) -> bool:
    return any(isinstance(n, ast.Attribute) and n.attr == "_repo" for n in ast.walk(knoop))


def test_beproef_raakt_de_repository_niet() -> None:
    for naam in ZONDER_DATABASE:
        assert not _raakt_de_repository(_methode(naam)), (
            f"{DIENST}::{naam} gebruikt `self._repo`, maar draait NA het sluiten van de "
            "databasesessie. Een sessie die dicht is gaat daar stil weer open en checkt een "
            "verbinding uit die niemand teruggeeft -- zonder foutmelding, op de database die "
            "deze splitsing juist moest ontlasten."
        )


def test_de_databasehelft_gebruikt_de_repository_WEL() -> None:
    """De tegenrichting. Zonder deze helft is 'haal de repository overal weg' geldig."""
    for naam in MET_DATABASE:
        assert _raakt_de_repository(_methode(naam)), (
            f"{DIENST}::{naam} raakt de repository niet meer. Deze bewaker eist alleen dat het "
            "netwerkdeel schoon is; als het databasedeel zijn werk niet meer doet, is de "
            "splitsing zinloos geworden."
        )
