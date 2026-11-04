"""`_hitl_ticket_ref` mag maar op EEN plek in een payload gezet worden (ADR-036 H-1).

**Waarom deze guard bestaat.** `ToolBrokerService.execute_tool` commit sinds 2026-08-09 de
sessie zodra een HITL-ticket is verzilverd, zodat de verzilvering vastligt voordat de tool
draait. De rechtvaardiging dat die commit veilig is, rust volledig op een MEETING: er is exact
een plek die `_hitl_ticket_ref` in een payload zet (`hitl_router.py`), en op dat pad heeft de
sessie op dat moment niets anders openstaan -- de goedkeuring is al vastgelegd.

Een meting roest. Zodra een tweede plek die sleutel gaat zetten, kan `execute_tool` een commit
doen midden in een transactie die wel degelijk ander werk openheeft staan, en dan legt hij
werk vast dat de aanroeper nog had willen kunnen terugrollen. Deze guard laat dat niet
stilzwijgend gebeuren.

**Toetst STRUCTUUR, geen tekst.** Een `ast.Dict`-sleutel of een toewijzing
`payload["_hitl_ticket_ref"] = ...`. Bewust NIET "de string komt voor in het bestand": dan
houdt een comment, een docstring of een lees-aanroep (`payload.get(...)`, de
redactie-toelaatlijsten) de guard bezig met dingen die niets produceren. Dat is exact de
faalvorm waar deze sprintdag over gaat.

**Mutatietest (2026-08-09, beide richtingen):**
- In `src/core/copilot/service.py` een `payload = {"_hitl_ticket_ref": ref}` toegevoegd -> ROOD.
- In datzelfde bestand een `payload["_hitl_ticket_ref"] = ref` toegevoegd -> ROOD.
- LEGITIEM: een LEES-aanroep `payload.get("_hitl_ticket_ref")` toegevoegd -> GROEN.
- LEGITIEM: de naam in een comment genoemd -> GROEN.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_SLEUTEL = "_hitl_ticket_ref"

#: Plekken die deze sleutel BEWUST in een payload zetten, met reden per regel.
#: Een lijst van precies een, en dat is het punt.
KNOWN_PRODUCERS: dict[str, str] = {
    "src/core/api/v1/tool_broker/hitl_router.py": (
        "2026-08-09 -- de goedkeurroute geeft de ticketverwijzing mee zodat de poort in "
        "execute_tool het ticket verzilvert. Dit is het pad waarop de commit-na-verzilvering "
        "veilig is: de goedkeuring is daar al vastgelegd (hitl_router.py:402)."
    ),
}


def _kandidaatbestanden() -> list[Path]:
    """Bronbestanden die de sleutel noemen, via `git grep` als bewijsbare superset.

    Bewust `git grep` en niet zelf de boom inlezen: een test die alle getrackte bestanden in
    Python leest heeft eerder een xdist-worker omgebracht, wat zich voordeed als willekeurige
    failures elders (ADR-036 OP-19/OP-46).
    """
    resultaat = subprocess.run(
        ["git", "grep", "-l", "-I", "-F", _SLEUTEL, "--", "src/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return [REPO_ROOT / regel for regel in resultaat.stdout.split("\n") if regel.strip()]


def _zet_de_sleutel(pad: Path) -> bool:
    """Zet dit bestand de sleutel in een dict? (dict-literal of item-toewijzing)"""
    try:
        boom = ast.parse(pad.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False

    for knoop in ast.walk(boom):
        # `{"_hitl_ticket_ref": iets}` -- ook binnen een `{**parameters, ...}`.
        if isinstance(knoop, ast.Dict):
            for sleutel in knoop.keys:
                if isinstance(sleutel, ast.Constant) and sleutel.value == _SLEUTEL:
                    return True
        # `payload["_hitl_ticket_ref"] = iets`
        if isinstance(knoop, ast.Assign):
            for doel in knoop.targets:
                if (
                    isinstance(doel, ast.Subscript)
                    and isinstance(doel.slice, ast.Constant)
                    and doel.slice.value == _SLEUTEL
                ):
                    return True
    return False


def test_the_scan_finds_the_key_at_all() -> None:
    """Vangnet: loopt de scan leeg, dan bewaakt de test hieronder niets."""
    gevonden = _kandidaatbestanden()

    assert gevonden, (
        f"Geen enkel bestand in src/ noemt {_SLEUTEL!r}. Is de sleutel hernoemd? Zolang dit "
        "leeg terugkomt is de guard hieronder betekenisloos."
    )


def test_the_known_producer_is_actually_detected() -> None:
    """Tweede vangnet: herkent de detector de BEKENDE producent nog?

    Zonder deze toets zou een detector die niets meer vindt (hernoemde AST-vorm, andere
    payload-constructie) groen melden dat er geen tweede producent is -- terwijl hij ook de
    eerste niet meer ziet. Dat is de vacuumval.
    """
    for pad in KNOWN_PRODUCERS:
        bestand = REPO_ROOT / pad
        assert bestand.exists(), f"{pad} bestaat niet meer; werk KNOWN_PRODUCERS bij."
        assert _zet_de_sleutel(bestand), (
            f"{pad} staat als producent van {_SLEUTEL!r} in de lijst, maar de detector vindt de "
            "sleutel daar niet meer als dict-sleutel of item-toewijzing. Of de code is "
            "veranderd, of de detector meet niets meer -- in beide gevallen bewaakt de test "
            "hieronder niets."
        )


def test_no_second_place_puts_the_ticket_ref_in_a_payload() -> None:
    """De kern: een tweede producent maakt de commit in `execute_tool` onveilig."""
    producenten = [
        pad.relative_to(REPO_ROOT).as_posix()
        for pad in _kandidaatbestanden()
        if _zet_de_sleutel(pad)
    ]
    onbekend = sorted(set(producenten) - set(KNOWN_PRODUCERS))

    assert not onbekend, (
        f"Deze bestanden zetten {_SLEUTEL!r} nu ook in een payload: {onbekend}.\n\n"
        "`ToolBrokerService.execute_tool` commit de sessie zodra een ticket is verzilverd, om "
        "de verzilvering vast te leggen voordat de tool draait (ADR-036 H-1). Dat is veilig "
        "zolang de enige aanroeper op dat moment niets anders openstaan heeft. Een nieuwe "
        "producent betekent een nieuw pad, en daar kan die commit werk vastleggen dat de "
        "aanroeper nog had willen kunnen terugrollen.\n\n"
        "Controleer dat pad en zet het met datum en reden in KNOWN_PRODUCERS, of geef de "
        "ticketverwijzing niet mee."
    )


def test_known_producers_is_not_stale() -> None:
    """Een producent die is verdwenen MOET uit de lijst, anders rot die dicht."""
    verdwenen = [pad for pad in KNOWN_PRODUCERS if not (REPO_ROOT / pad).exists()]

    assert not verdwenen, (
        f"Deze bestanden staan in KNOWN_PRODUCERS maar bestaan niet meer: {verdwenen}. Haal ze "
        "uit de lijst; anders suggereert die lijst een uitzondering die nergens op slaat."
    )
