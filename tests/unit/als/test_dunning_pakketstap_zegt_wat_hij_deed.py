"""Stap 3 van mkb.zero_admin (dunning) zegt eerlijk wat hij deed (zero-admin afwerken, 2026-10-19).

Gemeten VOOR de reparatie (acceptatie btw-overzicht, en hier opnieuw met een scriptdubbel voor het taalmodel): de
stap gaf een resultaat zonder enige telling. Antwoordt het model zonder TOOL_CALL, dan is `result_data` alleen
`{"output": <modeltekst>, "tool_calls": 0}`: de uitslag meldde "Gelukt" terwijl er niets was gedaan en niemand wist
of er vorderingen openstonden. Nu draagt het resultaat twee tellingen die NIET van het model komen:

- `openstaand`: het aantal vorderingen van DEZE tenant dat nog niet betaald is (`None` als het tellen mislukte);
- `voorgesteld`: het aantal herinneringen dat in deze run als goedkeuringsticket is klaargezet.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tests.fixtures.llm_dubbel import als_async

TENANT = 1
INITIATOR = 42

_VOORBEELD = {
    "success": True,
    "params": {
        "receivable_id": 7,
        "kind": "herinnering",
        "recipient_email": "klant@voorbeeld.example",
        "subject": "Herinnering: factuur F-7",
        "body": "Beste klant, ...",
    },
}
_VERSTUREN = 'TOOL_CALL: send_payment_reminder {"receivable_id": 7, "kind": "herinnering"}'
_GEEN_ACTIE = "Er is niets te doen."

_REGISTRY = (
    "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry.execute_receivables_tool"
)


def _vordering(receivable_id: int, status: str) -> dict[str, object]:
    return {
        "receivable_id": receivable_id,
        "invoice_number": f"F-{receivable_id}",
        "amount": "100.00",
        "currency": "EUR",
        "due_date": "2026-09-01",
        "status": status,
    }


def _lijst(*vorderingen: dict[str, object], afgekapt: bool = False) -> dict[str, object]:
    return {
        "success": True,
        "receivables": list(vorderingen),
        "count": len(vorderingen),
        "truncated": afgekapt,
    }


def _tool(*vorderingen: dict[str, object]) -> AsyncMock:
    """Een registry die het statusfilter en de limiet van `list_receivables` nabootst (vaste volgorde)."""

    async def _antwoord(
        naam: str, payload: dict[str, object], *, tenant_id: int
    ) -> dict[str, object]:
        rijen = [v for v in vorderingen if payload.get("status") in (None, v["status"])]
        limiet = int(payload.get("limit", 50))  # type: ignore[call-overload]
        zichtbaar = rijen[:limiet]
        return {
            "success": True,
            "receivables": zichtbaar,
            "count": len(zichtbaar),
            "truncated": len(rijen) > limiet,
        }

    return AsyncMock(side_effect=_antwoord)


def _agent(antwoord: str) -> Any:
    from src.core.als.agents.skills.dunning import DunningSkill

    agent = DunningSkill(tenant_id=TENANT)
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=antwoord)
    agent._get_llm_service = als_async(llm)  # type: ignore[method-assign]
    return agent


async def _draai(antwoord: str, registry: AsyncMock) -> dict[str, Any]:
    agent = _agent(antwoord)
    with (
        patch(_REGISTRY, registry),
        patch(
            "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
            "preview_payment_reminder",
            AsyncMock(return_value=_VOORBEELD),
        ),
    ):
        resultaat = await agent.execute_with_manifest_prompt(
            {"task": "herinner de klant"}, initiated_by_user_id=INITIATOR
        )
    return resultaat.result_data or {}


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeStapTeltWatErIsGedaan:
    async def test_no_open_receivables_is_counted_as_zero(self) -> None:
        registry = AsyncMock(return_value=_lijst())

        data = await _draai(_GEEN_ACTIE, registry)

        assert (data["openstaand"], data["voorgesteld"]) == (0, 0)

    async def test_the_open_receivables_are_counted(self) -> None:
        registry = _tool(_vordering(1, "open"), _vordering(2, "herinnerd"))

        data = await _draai(_GEEN_ACTIE, registry)

        assert data["openstaand"] == 2

    async def test_a_paid_receivable_is_not_open(self) -> None:
        registry = _tool(_vordering(1, "betaald"), _vordering(2, "open"))

        data = await _draai(_GEEN_ACTIE, registry)

        assert data["openstaand"] == 1

    async def test_the_count_is_read_for_the_tenant_of_the_skill(self) -> None:
        registry = AsyncMock(return_value=_lijst())

        await _draai(_GEEN_ACTIE, registry)

        tenants = [aanroep.kwargs["tenant_id"] for aanroep in registry.await_args_list]
        assert tenants == [TENANT, TENANT, TENANT]

    async def test_a_truncated_list_is_reported_as_such(self) -> None:
        registry = _tool(*[_vordering(i, "open") for i in range(1, 202)])

        data = await _draai(_GEEN_ACTIE, registry)

        assert (data["openstaand"], data["openstaand_afgekapt"]) == (200, True)

    async def test_many_paid_receivables_do_not_hide_an_open_one(self) -> None:
        # De tool geeft de eerste 200 rijen op vervaldatum, betaald of niet: zonder statusfilter stonden hier 250
        # betaalde vorderingen voor een open en zei het scherm "Geen openstaande vorderingen".
        betaald = [_vordering(i, "betaald") for i in range(1, 251)]
        registry = _tool(*betaald, _vordering(999, "open"))

        data = await _draai(_GEEN_ACTIE, registry)

        assert data["openstaand"] == 1

    @pytest.mark.parametrize("status", ["open", "herinnerd", "geescaleerd"])
    async def test_a_truncated_list_of_any_open_status_is_reported(self, status: str) -> None:
        registry = _tool(*[_vordering(i, status) for i in range(1, 202)])

        data = await _draai(_GEEN_ACTIE, registry)

        assert (data["openstaand"], data.get("openstaand_afgekapt")) == (200, True)

    async def test_each_open_status_is_counted(self) -> None:
        registry = _tool(
            _vordering(1, "open"), _vordering(2, "herinnerd"), _vordering(3, "geescaleerd")
        )

        data = await _draai(_GEEN_ACTIE, registry)

        assert data["openstaand"] == 3

    async def test_zero_open_receivables_is_never_reported_as_truncated(self) -> None:
        registry = _tool(*[_vordering(i, "betaald") for i in range(1, 251)])

        data = await _draai(_GEEN_ACTIE, registry)

        assert (data["openstaand"], "openstaand_afgekapt" in data) == (0, False)

    async def test_a_failing_status_makes_the_whole_count_unknown(self) -> None:
        async def _kapot(
            naam: str, payload: dict[str, object], *, tenant_id: int
        ) -> dict[str, object]:
            if payload.get("status") == "herinnerd":
                return {"success": False, "error": "mislukt"}
            return {"success": True, "receivables": [], "count": 0, "truncated": False}

        data = await _draai(_GEEN_ACTIE, AsyncMock(side_effect=_kapot))

        assert data["openstaand"] is None

    async def test_a_ticket_text_in_a_tool_failure_is_not_counted(self) -> None:
        # Een foutmelding die de zin van een ticket nabootst (bijvoorbeeld via een door het model gekozen waarde)
        # is geen klaargezet ticket: alleen de melding van de governance-poort telt.
        agent = _agent(_VERSTUREN)
        nep = {
            "success": False,
            "error": "goedkeuringsticket aangemaakt: hitl_abc123",
        }
        with (
            patch(_REGISTRY, _tool()),
            patch(
                "src.core.tool_broker.receivables_registry.ReceivablesToolRegistry."
                "preview_payment_reminder",
                AsyncMock(return_value=nep),
            ),
        ):
            resultaat = await agent.execute_with_manifest_prompt(
                {"task": "herinner"}, initiated_by_user_id=INITIATOR
            )

        assert (resultaat.result_data or {})["voorgesteld"] == 0

    async def test_a_failing_count_is_unknown_and_not_zero(self) -> None:
        registry = AsyncMock(return_value={"success": False, "error": "debiteuren lezen mislukt"})

        data = await _draai(_GEEN_ACTIE, registry)

        assert data["openstaand"] is None

    async def test_a_crashing_count_is_unknown_and_does_not_break_the_step(self) -> None:
        registry = AsyncMock(side_effect=RuntimeError("database weg"))

        data = await _draai(_GEEN_ACTIE, registry)

        assert (data["openstaand"], data["voorgesteld"]) == (None, 0)

    async def test_a_reminder_that_waits_for_approval_is_counted_as_proposed(
        self, hitl_ticket_repository: AsyncMock
    ) -> None:
        registry = _tool(_vordering(7, "open"))

        data = await _draai(_VERSTUREN, registry)

        assert (data["voorgesteld"], data["openstaand"]) == (1, 1)
        assert hitl_ticket_repository.create_hitl_request.await_count == 1

    async def test_the_model_text_does_not_decide_the_counts(self) -> None:
        registry = AsyncMock(return_value=_lijst())

        data = await _draai("Ik stelde 5 herinneringen voor en 9 vorderingen staan open.", registry)

        assert (data["openstaand"], data["voorgesteld"]) == (0, 0)

    async def test_the_existing_keys_of_the_result_stay(self) -> None:
        registry = AsyncMock(return_value=_lijst())

        data = await _draai(_GEEN_ACTIE, registry)

        assert data["tool_calls"] == 0
