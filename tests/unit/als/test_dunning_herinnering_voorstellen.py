"""De debiteurenagent starten voor gekozen facturen (debiteurenagent dag 3).

`DunningSkill.propose_reminders` is wat de knop "Herinnering voorstellen" aanroept. Er zit geen
taalmodel tussen: de mens heeft al gekozen WAT er moet gebeuren (welke factuur, welke soort
brief). De actie loopt wel langs dezelfde keten als elke agentactie: sjabloon, Council, de
HITL-vloer, en pas na goedkeuring de broker.

Autouse-opstelling uit `tests/unit/als/conftest.py`: Council keurt goed, `hitl_ticket_repository`
legt vast OF en MET WELKE parameters er een ticket komt. Zie `test_dunning_hotl_meting.py`.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

TENANT = 3
AANVRAGER = 77


def _voorbeeld(rid: int) -> dict[str, Any]:
    return {
        "success": True,
        "params": {
            "receivable_id": rid,
            "kind": "herinnering",
            "recipient_name": "Klant",
            "recipient_email": "klant@voorbeeld.example",
            "subject": f"Herinnering: factuur F-{rid}",
            "body": "Beste Klant, ...",
        },
    }


def _patch_voorbeeld() -> Any:
    async def _maak(self: Any, tenant_id: int, rid: Any, kind: Any) -> dict[str, Any]:
        return _voorbeeld(int(rid))

    return patch(
        "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
        "preview_payment_reminder",
        _maak,
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestVoorstellen:
    async def test_every_chosen_receivable_becomes_one_ticket(
        self, hitl_ticket_repository: AsyncMock
    ) -> None:
        from src.core.als.agents.skills.dunning import DunningSkill

        with _patch_voorbeeld():
            await DunningSkill(tenant_id=TENANT).propose_reminders(
                [11, 12], "herinnering", initiated_by_user_id=AANVRAGER
            )

        ids = [
            c.kwargs["action_params"]["receivable_id"]
            for c in hitl_ticket_repository.create_hitl_request.await_args_list
        ]
        assert ids == [11, 12]

    async def test_a_repeated_receivable_gives_one_ticket(
        self, hitl_ticket_repository: AsyncMock
    ) -> None:
        from src.core.als.agents.skills.dunning import DunningSkill

        with _patch_voorbeeld():
            await DunningSkill(tenant_id=TENANT).propose_reminders(
                [11, 11], "herinnering", initiated_by_user_id=AANVRAGER
            )

        assert hitl_ticket_repository.create_hitl_request.await_count == 1

    async def test_the_person_who_started_it_is_the_requester(
        self, hitl_ticket_repository: AsyncMock
    ) -> None:
        from src.core.als.agents.skills.dunning import DunningSkill

        with _patch_voorbeeld():
            await DunningSkill(tenant_id=TENANT).propose_reminders(
                [11], "herinnering", initiated_by_user_id=AANVRAGER
            )

        kwargs = hitl_ticket_repository.create_hitl_request.await_args.kwargs
        assert (kwargs["user_id"], kwargs["tenant_id"]) == (AANVRAGER, TENANT)

    async def test_the_answer_names_the_ticket_per_receivable(
        self, hitl_ticket_repository: AsyncMock
    ) -> None:
        from src.core.als.agents.skills.dunning import DunningSkill

        hitl_ticket_repository.create_hitl_request.return_value = "hitl_0123456789abcdef"
        with _patch_voorbeeld():
            uit = await DunningSkill(tenant_id=TENANT).propose_reminders(
                [11], "herinnering", initiated_by_user_id=AANVRAGER
            )

        assert uit == [
            {
                "receivable_id": 11,
                "status": "wacht_op_goedkeuring",
                "ticket_ref": "hitl_0123456789abcdef",
            }
        ]

    async def test_an_unknown_receivable_gives_no_ticket_and_says_so(
        self, hitl_ticket_repository: AsyncMock
    ) -> None:
        from src.core.als.agents.skills.dunning import DunningSkill

        with patch(
            "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
            "preview_payment_reminder",
            AsyncMock(return_value={"success": False, "error": "bestaat niet"}),
        ):
            uit = await DunningSkill(tenant_id=TENANT).propose_reminders(
                [99], "herinnering", initiated_by_user_id=AANVRAGER
            )

        assert hitl_ticket_repository.create_hitl_request.await_count == 0
        assert uit[0]["status"] == "niet_gelukt"

    async def test_the_initiator_is_cleared_afterwards(
        self, hitl_ticket_repository: AsyncMock
    ) -> None:
        from src.core.als.agents.skills.dunning import DunningSkill

        agent = DunningSkill(tenant_id=TENANT)
        with _patch_voorbeeld():
            await agent.propose_reminders([11], "herinnering", initiated_by_user_id=AANVRAGER)

        assert agent._initiated_by_user_id is None


@pytest.mark.unit
def test_the_agent_resolves_for_a_brand_new_tenant() -> None:
    """Er is geen registratie per tenant: de catalogus en de bedrading zijn globaal (gemeten)."""
    from src.core.als.agents.loader import EnterpriseCatalogLoader
    from src.core.als.agents.skills.dunning import DunningSkill
    from src.core.als.enterprise.packs import _PILOT_WIRED_AGENT_IDS

    agent = EnterpriseCatalogLoader().load_all().get_agent_instance("dunning", 987654)

    assert isinstance(agent, DunningSkill) and "dunning" in _PILOT_WIRED_AGENT_IDS
