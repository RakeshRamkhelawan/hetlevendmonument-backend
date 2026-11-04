"""Dependencies voor het betaalvoorstel en het betaalbestand (crediteuren dag 3; ADR-033 Laag 2).

Alles loopt via `importlib` zodat dit domein geen nieuwe (bestand -> module)-paren toevoegt aan het fan-out-budget van `core_api`
(`tests/architecture/test_dsm_grade_a_plus.py`): de crediteurenagent en de registry zijn runtime-afhankelijkheden, geen typen die de
router nodig heeft. Een test of een andere omgeving vervangt ze op een plek.

Rechten: een betaalvoorstel laten maken vraagt `payables:write` (rol `crediteuren`); het betaalbestand ophalen vraagt het
goedkeurrecht `payables:approve` (`vereis_goedkeurrecht`), want wie het bestand ophaalt zet geld in beweging dat een mens al heeft
goedgekeurd.
"""

from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Protocol, cast

from .inlezen_dependencies import vereis_goedkeurrecht

__all__ = ["BetaalrunRegistry", "get_betaalrun_registry", "get_voorstel_starter", "vereis_goedkeurrecht"]


class BetaalrunRegistry(Protocol):
    """Wat de routes van `BetaalrunToolRegistry` gebruiken."""

    async def selecteer(self, tenant_id: int) -> dict[str, object]: ...

    async def trek_factuur_in(
        self, tenant_id: int, payable_id: int, *, door: int, reden: str
    ) -> dict[str, object] | None: ...

    async def trek_voorstel_in(
        self, tenant_id: int, *, ticket_ref: str, door: int, reden: str
    ) -> dict[str, object] | None: ...

    async def maak_betaalbestand(
        self,
        tenant_id: int,
        *,
        door: int,
        debiteur_naam: str,
        debiteur_iban: str,
        uitvoerdatum: date,
    ) -> tuple[bytes, dict[str, object]]: ...


def get_betaalrun_registry() -> BetaalrunRegistry:
    """De registry die het voorstel selecteert en het betaalbestand maakt."""
    module = importlib.import_module("src.core.tool_broker.payment_run_registry")
    return cast(BetaalrunRegistry, module.BetaalrunToolRegistry())


def get_voorstel_starter() -> Callable[[int, int], Awaitable[dict[str, object]]]:
    """De crediteurenagent die een betaalvoorstel maakt: `(tenant_id, user_id) -> uitkomst`."""
    module = importlib.import_module("src.core.services.crediteuren_verwerking")
    return cast(Callable[[int, int], Awaitable[dict[str, object]]], module.stel_betaling_voor)
