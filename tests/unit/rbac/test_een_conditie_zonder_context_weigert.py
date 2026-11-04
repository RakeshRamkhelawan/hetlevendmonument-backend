"""Een voorwaardelijk recht zonder context wordt GEWEIGERD, niet toegekend (ADR-036 OP-257).

WAT HIER MIS WAS
----------------
`_evaluate_conditions` eindigde op `# Default: conditions met` gevolgd door `return True`.
De takken die `owner_only` en `same_tenant` afhandelen eisen allebei `resource_id` EN
`resource_type`; ontbreekt er een, dan worden die takken overgeslagen en gaf de staart
`True`. Een permissierij met `owner_only: true` werd dus ONVOORWAARDELIJK toegekend zodra
de aanroeper geen resource meegaf -- precies het tegenovergestelde van wat die conditie
bedoelt.

Hetzelfde gold voor een `resource_type` die hierboven niet wordt afgehandeld: alles wat
geen `agent` of `workflow` is, viel door naar `True`.

**Dit was gemeten ONBEREIKBAAR op 2026-09-18** -- geen enkele aanroeper van
`user_has_permission` gaf `resource_id`/`resource_type` mee, en er stond nul permissierijen
met condities in de database. Daarom stond het als latente bevinding in het register en
niet als incident. Gedicht voordat iemand de eerste conditionele rij aanmaakt, want daarna
is het een actief gat en geen latent.

MUTATIEBEWIJS (2026-09-18, beide richtingen, een regel per bewaakte conditie)
----------------------------------------------------------------------------
    `return False` in de staart terug naar `return True`  -> ROOD op owner_only EN same_tenant
    de `afdwingbaar`-verzameling leeggemaakt              -> ROOD (dan weigert hij nooit)
    een rij ZONDER afdwingbare condities                  -> GROEN, er valt niets te weigeren
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.services.rbac_service import RBACService

GEBRUIKER = 7


def _dienst() -> RBACService:
    sessie = MagicMock()
    sessie.execute = AsyncMock()
    return RBACService(sessie)


@pytest.mark.asyncio
@pytest.mark.parametrize("conditie", ["owner_only", "same_tenant"])
async def test_zonder_resourcecontext_wordt_een_conditie_geweigerd(conditie: str) -> None:
    """De conditie kan niet worden beoordeeld, dus het antwoord is nee."""
    uitkomst = await _dienst()._evaluate_conditions(
        {conditie: True}, GEBRUIKER, resource_id=None, resource_type=None
    )

    assert uitkomst is False, (
        f"Een permissierij met `{conditie}` werd toegekend terwijl de resource onbekend is. "
        "Dan betekent de conditie niets meer en geeft het recht onvoorwaardelijk toegang "
        "(ADR-036 OP-257)."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("conditie", ["owner_only", "same_tenant"])
async def test_een_onbekend_resourcetype_wordt_ook_geweigerd(conditie: str) -> None:
    """Alles wat geen `agent` of `workflow` is, viel eerder door naar True."""
    uitkomst = await _dienst()._evaluate_conditions(
        {conditie: True}, GEBRUIKER, resource_id=42, resource_type="iets_onbekends"
    )

    assert uitkomst is False


@pytest.mark.asyncio
async def test_zonder_afdwingbare_condities_blijft_het_ja() -> None:
    """De tegenrichting: zonder deze helft zou 'weiger alles' een geldige oplossing zijn."""
    uitkomst = await _dienst()._evaluate_conditions(
        {"max_count": 5}, GEBRUIKER, resource_id=None, resource_type=None
    )

    assert uitkomst is True, (
        "Een rij zonder `owner_only` of `same_tenant` heeft niets dat beoordeeld moet "
        "worden; die mag niet ineens geweigerd worden."
    )


@pytest.mark.asyncio
async def test_een_conditie_die_op_false_staat_telt_niet_mee() -> None:
    """`owner_only: false` is geen eis, dus er valt niets te weigeren."""
    uitkomst = await _dienst()._evaluate_conditions(
        {"owner_only": False}, GEBRUIKER, resource_id=None, resource_type=None
    )

    assert uitkomst is True
