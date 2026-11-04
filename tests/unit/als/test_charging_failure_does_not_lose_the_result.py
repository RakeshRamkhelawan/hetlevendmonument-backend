"""Een mislukte afrekening gooit het geleverde resultaat niet weg (SP-COUNCIL-GATE-001).

Gate 2-ronde 3: de `except`-tak rond `charge_prana` was toegevoegd zonder test, en een stille
slikker zonder test is precies de vorm die een latere regressie onzichtbaar maakt.

De situatie is echt mogelijk sinds `charge_prana` een `ValueError` gooit als geen rij wordt
geraakt -- een tenant die tussen de budgetcontrole en de afrekening verdwijnt. Zonder de vangst
zou de gebruiker dan een onbehandelde fout krijgen in plaats van het antwoord waar hij al voor
betaald heeft.

Twee eigenschappen, allebei nodig:
1. Het resultaat komt gewoon terug (anders is de vangst zinloos).
2. De fout wordt op ERROR gelogd met stacktrace (anders is het een gat in de financiele
   governance dat niemand ziet -- er is geen tegenboeking en geen metric, dus alertering op
   deze logregel is de enige detectie, ADR-036 OP-141).

**Mutatietest (2026-08-16), beide richtingen:**
- De `try/except` weggehaald -> ROOD op `test_the_result_survives_a_failed_charge`
  (de `ValueError` propageert).
- `logger.error` naar `logger.debug` -> ROOD op `test_the_failure_is_logged_loudly`.
- Ongewijzigd -> beide GROEN, en `test_a_successful_charge_logs_no_error` borgt dat de guard
  niet altijd een fout ziet.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

PILOT_TENANT = 1
PILOT_USER = 42


def _agent() -> Any:
    from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

    agent = SkillsGapTrainingSkill(tenant_id=PILOT_TENANT)
    agent._initiated_by_user_id = PILOT_USER
    return agent


async def _draai(agent: Any, *, charge_faalt: bool) -> Any:
    """Draai een geslaagde uitvoering binnen het budget, met een al dan niet falende afrekening."""
    from src.core.shared.interfaces import ExecutionResult

    guard: Any = AsyncMock()
    guard.check_budget = AsyncMock()
    guard.charge_prana = AsyncMock(
        side_effect=ValueError("Tenant 1 not found") if charge_faalt else None
    )

    async def _werk() -> ExecutionResult:
        return ExecutionResult(
            task_id="t-1",
            success=True,
            output="klaar",
            tenant_id=PILOT_TENANT,
            agent_id=agent.agent_id,
        )

    with patch.object(agent, "_get_prana_guard", return_value=guard):
        return await agent._run_within_budget(_werk, task_id="t-1")


@pytest.mark.unit
@pytest.mark.asyncio
class TestAFailedChargeDoesNotDestroyTheResult:
    async def test_the_result_survives_a_failed_charge(self) -> None:
        """Het werk is geleverd; de boekhouding mag dat niet ongedaan maken."""
        resultaat = await _draai(_agent(), charge_faalt=True)

        assert resultaat.success is True, (
            "Een mislukte afrekening liet de uitvoering falen. De gebruiker verliest dan een "
            "antwoord dat er al was."
        )
        assert resultaat.output == "klaar"

    async def test_the_failure_is_logged_loudly(self, caplog: pytest.LogCaptureFixture) -> None:
        """Stil slikken is geen optie: dit is de enige detectie die er is."""
        with caplog.at_level(logging.ERROR, logger="src.core.als.agents.specialist_base"):
            await _draai(_agent(), charge_faalt=True)

        fouten = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert fouten, (
            "Er is niets op ERROR gelogd. Een niet-geboekte uitvoering is een gat in de "
            "financiele governance; zonder logregel ziet niemand het."
        )
        assert any("prana" in r.getMessage().lower() for r in fouten), (
            f"De foutmelding noemt de afrekening niet: {[r.getMessage() for r in fouten]}"
        )
        assert any(r.exc_info for r in fouten), (
            "De logregel draagt geen stacktrace (`exc_info`), dus de oorzaak is niet te zien."
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestTheGuardIsNotAlwaysFiring:
    async def test_a_successful_charge_logs_no_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """De andere richting: zonder fout hoort er geen foutmelding te zijn."""
        with caplog.at_level(logging.ERROR, logger="src.core.als.agents.specialist_base"):
            resultaat = await _draai(_agent(), charge_faalt=False)

        assert resultaat.success is True
        prana_fouten = [
            r
            for r in caplog.records
            if r.levelno >= logging.ERROR and "prana" in r.getMessage().lower()
        ]
        assert not prana_fouten, (
            f"Een geslaagde afrekening logde toch een fout: {[r.getMessage() for r in prana_fouten]}"
        )
