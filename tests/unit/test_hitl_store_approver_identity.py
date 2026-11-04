"""De goedkeurder in een HITL-ticket mag niet verzonnen worden (ADR-036 OP-59).

**Wat er stond.** `hitl_store.get_ticket_async` zocht het e-mailadres van de goedkeurder op via
`select(User.email).where(User.id == ticket.resolved_by)`, en viel bij een lege uitkomst terug op de
literal `"approver@tenant1.com"` -- in beide takken, plus een kale `except Exception` die elke fout
opslokte en dezelfde literal zette.

**Waarom dat erger is dan testrommel in productiecode.** Dit veld is wat `/hitl/pending`,
`/hitl/audit`, de approve/reject-response en de websocket-uitzending tonen als de mens die een
HIGH-risk actie heeft goedgekeurd. OP-28 registreert het als de kern van het art.-14-toezicht, en
het valt buiten `compute_audit_hash`. Is de goedkeurende gebruiker inmiddels verwijderd, of faalt de
query, dan zei het toezichtsrecord dat `approver@tenant1.com` de actie heeft goedgekeurd. Dat is een
onware bewering op een gezaghebbende plek -- precies de klasse fout die deze sprint zes rondes lang
heeft opgeleverd, nu in de vorm van een vast e-mailadres.

Gevonden door de Taak 2-review, vlak voordat deze code voor het eerst geserveerd werd. Zolang de
router nul importeurs had, kwam dit veld nergens terecht.

**Wat er nu hoort te gebeuren:** geen naam als er geen naam is. Het veld is al `str | None`, en het
numerieke `resolved_by` (een FK naar `users.id`) is het eigenlijke bewijs -- het e-mailadres is
presentatie, en presentatie mag ontbreken.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

FORGED = "approver@tenant1.com"


def _ticket(status: str) -> MagicMock:
    ticket = MagicMock()
    ticket.ticket_ref = "TOOL-ABC12345"
    ticket.tenant_id = 1
    ticket.status = status
    ticket.tool_name = "local__run_shell"
    ticket.payload = {"_decision_id": "d-1", "_requested_by": "user:7"}
    ticket.risk_level = "HIGH"
    ticket.created_at = datetime.now(timezone.utc)
    ticket.expires_at = datetime.now(timezone.utc)
    ticket.resolved_at = datetime.now(timezone.utc)
    ticket.resolved_by = 42
    return ticket


async def _ticket_dict(status: str, monkeypatch: pytest.MonkeyPatch, *, user_found: bool) -> Any:
    """Haal het ticket op met een database die de gebruiker wel of niet kent."""
    from src.core.tool_broker import hitl_store

    class _Repo:
        def __init__(self, db: Any) -> None:
            self._db = db

        async def get(self, ticket_ref: str, tenant_id: int) -> MagicMock:
            return _ticket(status)

    monkeypatch.setattr(hitl_store, "HITLTicketRepository", _Repo)

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(
        return_value="echte.beheerder@klant.example" if user_found else None
    )
    db.execute = AsyncMock(return_value=result)

    return await hitl_store.get_ticket_async("TOOL-ABC12345", 1, db)


@pytest.mark.unit
class TestTheApproverIsNeverInvented:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status,field", [("approved", "approved_by"), ("rejected", "rejected_by")]
    )
    async def test_an_unknown_user_yields_no_name(
        self, status: str, field: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data = await _ticket_dict(status, monkeypatch, user_found=False)

        assert data is not None
        assert data.get(field) != FORGED, (
            f"`{field}` is ingevuld met de literal {FORGED!r} terwijl de gebruiker niet gevonden is. "
            "Dat is een verzonnen naam op het veld dat OP-28 registreert als de kern van het "
            "art.-14-toezicht. Laat het leeg; `resolved_by` (FK naar users.id) is het bewijs."
        )
        assert data.get(field) is None, (
            f"`{field}` is {data.get(field)!r} terwijl de gebruiker niet gevonden is. Verwacht None."
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status,field", [("approved", "approved_by"), ("rejected", "rejected_by")]
    )
    async def test_a_known_user_is_still_resolved(
        self, status: str, field: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vangnet: "altijd None" zou de test hierboven ook groen maken.

        Dan verdwijnt de leesbare naam van de goedkeurder uit elk scherm, en dat is niet de
        bedoeling -- alleen het VERZINNEN ervan is fout.
        """
        data = await _ticket_dict(status, monkeypatch, user_found=True)

        assert data is not None
        assert data.get(field) == "echte.beheerder@klant.example", (
            f"`{field}` is {data.get(field)!r} terwijl de gebruiker WEL gevonden is. De naam hoort "
            "gewoon opgelost te worden; alleen verzinnen mag niet."
        )
