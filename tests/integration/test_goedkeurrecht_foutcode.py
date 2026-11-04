"""De route geeft bij een ontbrekend goedkeurrecht 403 MET de foutcode APPROVAL_RIGHT_REQUIRED.

Hergebruikt de opzet van `test_goedkeuren_is_een_procesbevoegdheid.py`: echte app, echte
testdatabase, de rol bepaalt het recht.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.test_goedkeuren_is_een_procesbevoegdheid import (  # noqa: F401
    COLLEGA,
    _agent_vraagt_aan,
    _vraag,
    _zet_rollen,
    debiteur,
    rollen_hersteld,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestDeRouteGeeftDeFoutcode:
    async def test_listing_without_any_approval_right_has_the_error_code(
        self, debiteur: int, integration_app: Any
    ) -> None:
        await _zet_rollen(COLLEGA, ["user"])

        antwoord = await _vraag(integration_app, COLLEGA, "GET", "pending")

        assert antwoord.json()["error"]["error_code"] == "APPROVAL_RIGHT_REQUIRED", antwoord.text

    async def test_approving_without_the_process_right_has_the_error_code(
        self, debiteur: int, integration_app: Any
    ) -> None:
        ref = await _agent_vraagt_aan(debiteur)
        await _zet_rollen(COLLEGA, ["admin"])

        antwoord = await _vraag(integration_app, COLLEGA, "POST", "approve", {"ticket_ref": ref})

        assert antwoord.json()["error"]["error_code"] == "APPROVAL_RIGHT_REQUIRED", antwoord.text

    async def test_the_refusal_is_still_a_403(self, debiteur: int, integration_app: Any) -> None:
        await _zet_rollen(COLLEGA, ["user"])

        antwoord = await _vraag(integration_app, COLLEGA, "GET", "pending")

        assert antwoord.status_code == 403, antwoord.text
