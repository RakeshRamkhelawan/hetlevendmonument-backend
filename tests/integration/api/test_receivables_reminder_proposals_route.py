"""`POST /api/v1/receivables/reminder-proposals`: de debiteurenagent starten (dag 3).

Echte app-stack en echte `require_permission` op het JWT (Postgres, netwerkpoort 5455), zelfde
opstelling als `test_receivables_api_is_confined_to_its_tenant.py`. De agent zelf is hier een
dubbel: wat hij doet meet `tests/unit/als/test_dunning_herinnering_voorstellen.py`. Deze module
meet wat de ROUTE doorgeeft: de tenant uit de JWT, de ingelogde gebruiker als aanvrager, en
alleen geldige invoer.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.api.test_receivables_api_is_confined_to_its_tenant import api  # noqa: F401

URL = "/api/v1/receivables/reminder-proposals"


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    import importlib

    # De module, niet het `router`-object dat het pakket onder dezelfde naam exporteert.
    module = importlib.import_module("src.core.api.v1.receivables.router")

    aanroepen: list[dict[str, Any]] = []

    async def _start(**kwargs: Any) -> list[dict[str, object]]:
        aanroepen.append(kwargs)
        return [
            {"receivable_id": r, "status": "wacht_op_goedkeuring", "ticket_ref": "hitl_x"}
            for r in kwargs["receivable_ids"]
        ]

    monkeypatch.setattr(module, "start_reminder_proposals", _start)
    return aanroepen


@pytest.mark.integration
@pytest.mark.asyncio
class TestStarten:
    async def test_the_tenant_and_the_requester_come_from_the_token(
        self, api: AsyncClient, agent: list[dict[str, Any]]  # noqa: F811
    ) -> None:
        await api.post(URL, json={"receivable_ids": [5], "kind": "herinnering"})

        assert (agent[0]["tenant_id"], agent[0]["user_id"]) == (1, 1)

    async def test_the_answer_lists_the_outcome_per_receivable(
        self, api: AsyncClient, agent: list[dict[str, Any]]  # noqa: F811
    ) -> None:
        antwoord = await api.post(URL, json={"receivable_ids": [5, 6], "kind": "aanmaning"})

        assert [u["receivable_id"] for u in antwoord.json()["data"]] == [5, 6]

    async def test_a_tenant_id_in_the_body_is_refused(
        self, api: AsyncClient, agent: list[dict[str, Any]]  # noqa: F811
    ) -> None:
        antwoord = await api.post(
            URL, json={"receivable_ids": [5], "kind": "herinnering", "tenant_id": 2}
        )

        assert antwoord.status_code == 422 and agent == []

    async def test_an_unknown_kind_is_refused(
        self, api: AsyncClient, agent: list[dict[str, Any]]  # noqa: F811
    ) -> None:
        antwoord = await api.post(URL, json={"receivable_ids": [5], "kind": "dreigbrief"})

        assert antwoord.status_code == 422

    async def test_more_than_twenty_receivables_is_refused(
        self, api: AsyncClient, agent: list[dict[str, Any]]  # noqa: F811
    ) -> None:
        antwoord = await api.post(
            URL, json={"receivable_ids": list(range(1, 22)), "kind": "herinnering"}
        )

        assert antwoord.status_code == 422
