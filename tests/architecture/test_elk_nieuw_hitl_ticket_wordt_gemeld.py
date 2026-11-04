"""Elk nieuw HITL-ticket wordt live gemeld, op EEN plek, ongeacht het pad (meetlat-scenario 5).

**De bevinding (acceptant, 2026-10-05).** Een ticket uit `/debiteuren` kwam niet live binnen:
`notify_new_ticket` werd alleen in `tool_broker/router.py` aangeroepen, en het agentpad maakte
zijn ticket via `HITLTicketRepository.create_hitl_request` zonder melding.

**Wat deze guard bewaakt -- drie dingen, een test per ding:**

1. `HITLTicketRepository.create` roept `_meld_na_commit` aan. Elk pad maakt zijn ticket via
   `create()`, dus daar hoort de melding.
2. Alleen `hitl_repository.py` maakt een `HITLTicket(...)`-rij aan. Een tweede plek die het object
   zelf bouwt, loopt om de melding heen.
3. Geen enkel bestand in `src/` roept `notify_new_ticket` of `broadcast_new_ticket` aan, behalve
   de centrale plek. Een tweede kopie bij het aanmaken geeft een dubbele melding.

Het gedrag zelf (een echte websocket-client ontvangt het ticket uit het agentpad, een andere
tenant niets, een rollback meldt niets, een mislukte melding laat het aanmaken niet falen) staat
in `tests/integration/test_een_nieuw_ticket_komt_live_binnen.py`; die vraagt PostgreSQL. Deze
guard draait zonder database en dus in elke testpoort.

**Mutatiebewijs (2026-10-05, op een kopie, teruggezet uit die kopie):**

- Voorwaarts 1: de regel `_meld_na_commit(self._db, ticket_ref, tenant_id)` uit `create()`
  gehaald -> `test_create_meldt_het_ticket` ROOD.
- Voorwaarts 1b: de aanroep alleen in een comment laten staan -> ROOD (er wordt op `ast.Call`
  getoetst, niet op tekst).
- Voorwaarts 2: in `hitl_store.py` een `HITLTicket(ticket_ref=...)` toegevoegd ->
  `test_alleen_de_repository_bouwt_een_ticket` ROOD.
- Voorwaarts 3: `await notify_new_ticket(...)` teruggezet in `tool_broker/router.py` ->
  `test_er_is_geen_tweede_melding_bij_het_aanmaken` ROOD.
- Achterwaarts: `hitl_repository.py` zelf (definitie van `HITLTicket(` in `create`, en de import
  van `broadcast_new_ticket` in `_meld`) en de definities in `hitl_notifier.py` blijven GROEN; een
  `HITLTicket.ticket_ref`-attribuut in een query elders (`hitl_store.py`, `actors.py`) ook.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
REPOSITORY = SRC / "core" / "tool_broker" / "hitl_repository.py"
NOTIFIER = SRC / "core" / "tool_broker" / "hitl_notifier.py"

#: Functies die een NIEUW ticket melden; alleen de centrale plek mag ze aanroepen.
MELDERS = frozenset({"notify_new_ticket", "broadcast_new_ticket"})


def _naam(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _bronbestanden() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "activepieces" not in p.parts]


def _boom(pad: Path) -> ast.Module:
    return ast.parse(pad.read_text(encoding="utf-8"), filename=str(pad))


def _methode(boom: ast.Module, klasse: str, naam: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for knoop in boom.body:
        if isinstance(knoop, ast.ClassDef) and knoop.name == klasse:
            for lid in knoop.body:
                if isinstance(lid, (ast.FunctionDef, ast.AsyncFunctionDef)) and lid.name == naam:
                    return lid
    raise AssertionError(f"{klasse}.{naam} niet gevonden in {REPOSITORY}")


def test_create_meldt_het_ticket() -> None:
    create = _methode(_boom(REPOSITORY), "HITLTicketRepository", "create")
    aanroepen = {_naam(k) for k in ast.walk(create) if isinstance(k, ast.Call)}
    assert "_meld_na_commit" in aanroepen, (
        "HITLTicketRepository.create meldt een nieuw ticket niet meer live "
        "(_meld_na_commit ontbreekt). Elk pad maakt zijn ticket hier; zonder deze aanroep komt "
        "een ticket uit het agentpad niet binnen op /hitl (meetlat-scenario 5)."
    )


def test_alleen_de_repository_bouwt_een_ticket() -> None:
    buiten: list[str] = []
    for pad in _bronbestanden():
        if pad == REPOSITORY:
            continue
        for knoop in ast.walk(_boom(pad)):
            if isinstance(knoop, ast.Call) and _naam(knoop) == "HITLTicket":
                buiten.append(f"{pad.relative_to(REPO_ROOT).as_posix()}:{knoop.lineno}")
    assert not buiten, (
        "Een HITLTicket wordt buiten HITLTicketRepository.create gebouwd, en loopt daarmee om de "
        f"live melding heen: {buiten}. Gebruik HITLTicketRepository.create."
    )


def test_er_is_geen_tweede_melding_bij_het_aanmaken() -> None:
    gevonden: list[str] = []
    for pad in _bronbestanden():
        if pad in (REPOSITORY, NOTIFIER):
            continue
        for knoop in ast.walk(_boom(pad)):
            if isinstance(knoop, ast.Call) and _naam(knoop) in MELDERS:
                gevonden.append(f"{pad.relative_to(REPO_ROOT).as_posix()}:{knoop.lineno}")
    assert not gevonden, (
        "Een nieuw ticket wordt buiten de centrale plek gemeld; de client krijgt hem dan twee "
        f"keer: {gevonden}. De melding zit in HITLTicketRepository.create (_meld_na_commit)."
    )
