"""Een tool die `success: False` teruggeeft mag geen GESLAAGDE goedkeuring opleveren.

**Gemeten aanleiding (Gate 2-review 2026-09-21, HIGH-2).**
`hitl_router._voer_goedgekeurde_actie_uit` keek alleen naar uitzonderingen: zolang
`execute_tool` niet gooide, gaf hij `(True, None)` terug. Het toolcontract (BE-AGT-039 par. 3)
schrijft `{"success": false, "error": ...}` voor als foutvorm, en tot 2026-09-21 reisde er over
deze route geen enkele tool die die vorm gebruikte -- dus viel het niet op.

`schedule_training` gebruikt hem op zes takken (onbekend veld, ongeldige status, medewerker of
training bestaat niet binnen de tenant, ...). Zonder deze controle is het gevolg:

  mens keurt goed -> `redeem_approval` zet het ticket op `consumed` -> de tool weigert
  -> de API meldt GESLAAGD -> er staat geen rij in `employee_trainings`

Dat is succes zonder werk (ADR-036 par. 1) op het enige toezichtspunt dat dit systeem heeft, EN
de goedkeuring is verbruikt en niet herhaalbaar. Dezelfde fout is op het SKILLpad al onder
BE-AGT-044 gerepareerd (`specialist_base.py`); deze route was toen overgeslagen.

**Mutatiebewijs (2026-09-21, beide richtingen):**

1. De `if isinstance(resultaat, dict) and resultaat.get("success") is False`-tak uit
   `hitl_router.py` weghalen -> `test_a_refusing_tool_is_not_a_successful_approval` ROOD.
2. `is False` verbreden naar `is not True` -> `test_a_tool_without_a_success_field_still_counts`
   ROOD. Dat is de tegenrichting die telt: een tool die GEEN `success`-veld teruggeeft (de vier
   business-tools geven `{"success": True, "data": ...}`, maar een lokale tool mag ook een
   andere vorm hebben) mag niet ineens als mislukt gelden.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

TOOL = "schedule_training"
TICKET = "ticket-1"


class _Broker:
    """Een broker die exact EEN antwoord teruggeeft. Geen mock van het contract, een dubbelganger."""

    def __init__(self, antwoord: object) -> None:
        self._antwoord = antwoord
        self.aanroepen = 0

    async def execute_tool(self, **kwargs: object) -> object:
        self.aanroepen += 1
        return self._antwoord


async def _voer_uit(antwoord: object) -> tuple[bool, str | None]:
    from src.core.api.v1.tool_broker.hitl_router import _voer_goedgekeurde_actie_uit

    broker = _Broker(antwoord)
    geslaagd, classificatie = await _voer_goedgekeurde_actie_uit(
        broker,  # type: ignore[arg-type]
        ticket_ref=TICKET,
        tool_name=TOOL,
        parameters={"user_email": "a@b.test", "training_name": "X"},
        tenant_id=1,
        aangevraagd_door=7,
    )
    assert broker.aanroepen == 1, "De tool is niet aangeroepen; dan meet deze test niets."
    return geslaagd, classificatie


@pytest.mark.asyncio
async def test_a_refusing_tool_is_not_a_successful_approval() -> None:
    """`success: False` -> de goedkeuring is MISLUKT, met een classificatie."""
    geslaagd, classificatie = await _voer_uit(
        {"success": False, "error": "de medewerker bestaat niet binnen deze tenant"}
    )

    assert geslaagd is False, (
        "De route meldt succes terwijl de tool weigerde. Het ticket staat dan op `consumed`, "
        "er is niets geschreven, en de mens die goedkeurde ziet GESLAAGD."
    )
    assert classificatie == "tool_failure"


@pytest.mark.asyncio
async def test_the_error_text_never_leaves_the_route() -> None:
    """Alleen de CLASSIFICATIE gaat naar buiten; de foutTEKST kan payload-inhoud dragen."""
    smokkel = "Jan Jansen salaris 82000"
    _, classificatie = await _voer_uit({"success": False, "error": smokkel})

    assert classificatie is not None
    assert smokkel not in classificatie
    assert "Jansen" not in classificatie


@pytest.mark.asyncio
async def test_a_succeeding_tool_still_counts_as_successful() -> None:
    """De tegenrichting: een geslaagde tool blijft geslaagd."""
    geslaagd, classificatie = await _voer_uit({"success": True, "assigned": 1})

    assert geslaagd is True
    assert classificatie is None


@pytest.mark.asyncio
async def test_a_tool_without_a_success_field_still_counts() -> None:
    """De tweede tegenrichting, en de reden dat de controle `is False` gebruikt.

    Niet elke tool geeft een `success`-veld terug. Zou de controle `is not True` zijn, dan zou
    elk ander antwoordformaat ineens als mislukt gelden en zou een werkende goedkeuring
    terugkomen als fout -- "weiger alles" als geldige oplossing.
    """
    for antwoord in ({"data": [1, 2, 3]}, "platte tekst", None):
        geslaagd, classificatie = await _voer_uit(antwoord)
        assert geslaagd is True, f"antwoord {antwoord!r} werd ten onrechte als mislukt gezien"
        assert classificatie is None
