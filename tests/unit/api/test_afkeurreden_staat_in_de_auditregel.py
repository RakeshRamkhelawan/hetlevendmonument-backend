"""De afkeurreden staat in de auditregel `hitl_decision` (acceptant scenario 5, hertoets).

Gemeten 2026-10-05 (`05-audit-sql.txt`): regel 47 `rejected` had `details` `{}` en een
`event_metadata` zonder reden. Het toezicht kon dus niet terugzien WAAROM er is afgekeurd.
De reden gaat door dezelfde PII-opschoning als tekst naar een taalmodel
(`GDPREnforcer.redact_pii`), zodat er geen e-mailadres of IBAN in het auditlog belandt.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.unit.api.test_zelfgoedkeuring_volgt_de_vier_ogen_instelling import (
    COLLEGA,
    TICKET_REF,
    _client,
    _gebruiker,
    _ticket,
)

pytestmark = pytest.mark.usefixtures("procesrecht_voor_de_beslisser")


def _log_event(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from src.core.api.v1.tool_broker import hitl_router as module

    log_event = AsyncMock(return_value=True)
    monkeypatch.setattr(module.AuditService, "log_event", log_event)
    return log_event


def _afkeur_regel(log_event: AsyncMock) -> dict[str, object]:
    regels = [c.kwargs for c in log_event.await_args_list if c.kwargs.get("action") == "rejected"]
    assert len(regels) == 1
    return regels[0]


@pytest.mark.unit
def test_the_rejection_reason_is_in_the_audit_details(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(COLLEGA), vier_ogen=True)
    log_event = _log_event(monkeypatch)

    response = client.post(
        "/api/v1/tools/hitl/reject",
        json={"ticket_ref": TICKET_REF, "reason": "deze klant heeft al betaald"},
    )

    assert response.status_code == 200
    assert _afkeur_regel(log_event)["details"] == {"reason": "deze klant heeft al betaald"}


@pytest.mark.unit
def test_the_rejection_reason_is_cleaned_of_pii(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(COLLEGA), vier_ogen=True)
    log_event = _log_event(monkeypatch)

    client.post(
        "/api/v1/tools/hitl/reject",
        json={"ticket_ref": TICKET_REF, "reason": "al betaald, zie mail van jan@klant.nl"},
    )

    details = _afkeur_regel(log_event)["details"]
    assert isinstance(details, dict)
    assert "jan@klant.nl" not in str(details["reason"])
