"""Het dashboard vergelijkt de klant als GETAL met een getalskolom (ADR-036 OP-13, brief 2026-10-22).

**Wat er mis was (gemeten 2026-10-22 op een database uit de migratieketen).** Beide `get_dashboard_stats`-functies
(`src/core/api/analytics_endpoints.py` en `src/core/api/v1/analytics_ingest/dashboard_router.py`) zetten de klant om
naar tekst (`tenant_id_str = str(tenant_id)`) en vergeleken die met `WorkflowTemplate.tenant_id` en
`WorkflowExecution.tenant_id`, kolommen van het type INTEGER. PostgreSQL antwoordt daar op met
`operator does not exist: integer = character varying`; een `try/except` om elke query slikte de fout en het
dashboard toonde stilzwijgend nullen, voor elke klant.

**Wat hier bewezen wordt.** De waarde waartegen de klantkolom wordt vergeleken is het GETAL van de klant, in alle
queries van beide functies (twee op de sjablonen, twee op de uitvoeringen).

**Niet opgelost (staat in de oplevering).** Deze functies tellen de OUDE tabellen (`workflow_executions`,
`workflow_templates`); de uitvoeringen die de API en de engine maken staan in `c7_workflow_executions`. Het dashboard
blijft dus nullen tonen tot hij de goede tabel telt: dat is een productkeuze en een eigen brief.

**Mutatiebewijs:** zie de oplevering van de brief (per functie, beide richtingen).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.api import analytics_endpoints
from src.core.api.v1.analytics_ingest import dashboard_router

_FUNCTIES = [
    pytest.param(analytics_endpoints.get_dashboard_stats, id="analytics_endpoints"),
    pytest.param(dashboard_router.get_dashboard_stats, id="dashboard_router"),
]


def _db() -> tuple[MagicMock, list[Any]]:
    """Een database die elke query onthoudt en een lege uitkomst geeft."""
    uitgevoerd: list[Any] = []

    async def _execute(statement: Any, *_: Any, **__: Any) -> MagicMock:
        uitgevoerd.append(statement)
        resultaat = MagicMock()
        resultaat.scalar.return_value = 0
        resultaat.scalar_one.return_value = 0
        resultaat.scalars.return_value.all.return_value = []
        resultaat.all.return_value = []
        return resultaat

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db, uitgevoerd


def _klantwaarden(uitgevoerd: list[Any]) -> list[Any]:
    """De waarden waartegen een `tenant_id`-kolom in de uitgevoerde queries wordt vergeleken."""
    waarden: list[Any] = []
    for statement in uitgevoerd:
        try:
            parameters = statement.compile().params
        except Exception:  # noqa: BLE001 -- een query zonder te compileren parameters telt niet mee
            continue
        waarden.extend(w for k, w in parameters.items() if k.startswith("tenant_id"))
    return waarden


@pytest.mark.parametrize("functie", _FUNCTIES)
async def test_elke_klantvergelijking_gebruikt_het_getal_van_de_klant(functie: Any) -> None:
    db, uitgevoerd = _db()

    await functie(db=db, current_user=SimpleNamespace(id=1, tenant_id=7), tenant_id=7)

    waarden = _klantwaarden(uitgevoerd)
    assert (len(waarden) >= 2, {type(w).__name__ for w in waarden}, set(waarden)) == (
        True,
        {"int"},
        {7},
    )
