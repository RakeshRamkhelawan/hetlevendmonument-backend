"""Een door vier ogen geweigerde zelfbeslissing laat een auditregel achter (acceptant scenario 5).

Gemeten op dag 3: na de 403 stond er in `audit_logs` niets (`05-audit-hitl_decision.txt`
toont alleen besluiten). Een poging om een HIGH-risk actie zonder tweede paar ogen te
beslissen is precies wat het toezicht moet kunnen terugzien (SOUL principe 3; ADR-039: elke
handeling staat in het auditlog). De 403 blijft; de regel komt erbij, in `best_effort`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.unit.api.test_zelfgoedkeuring_volgt_de_vier_ogen_instelling import (
    AANVRAGER,
    COLLEGA,
    _client,
    _gebruiker,
    _keur_af,
    _keur_goed,
    _ticket,
)

pytestmark = pytest.mark.usefixtures("procesrecht_voor_de_beslisser")


def _schrijver(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from src.core.api.v1.tool_broker import hitl_router as module

    schrijver = AsyncMock(return_value=None)
    monkeypatch.setattr(module, "_write_audit_entry", schrijver)
    return schrijver


def _besluiten(schrijver: AsyncMock) -> list[str]:
    return [call.kwargs.get("decision") for call in schrijver.await_args_list]


@pytest.mark.unit
def test_a_refused_self_approval_is_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zelf goedkeuren met vier ogen aan: 403 en een regel 'refused_four_eyes'."""
    client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(AANVRAGER), vier_ogen=True)
    schrijver = _schrijver(monkeypatch)

    assert _keur_goed(client) == 403
    assert _besluiten(schrijver) == ["refused_four_eyes"]


@pytest.mark.unit
def test_a_refused_self_rejection_is_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zelf afkeuren met vier ogen aan: 403 en een regel 'refused_four_eyes'."""
    client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(AANVRAGER), vier_ogen=True)
    schrijver = _schrijver(monkeypatch)

    assert _keur_af(client) == 403
    assert _besluiten(schrijver) == ["refused_four_eyes"]


@pytest.mark.unit
def test_a_colleague_approval_writes_no_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """De andere kant: een collega die mag beslissen krijgt geen weigerregel."""
    client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(COLLEGA), vier_ogen=True)
    schrijver = _schrijver(monkeypatch)

    _keur_goed(client)
    assert "refused_four_eyes" not in _besluiten(schrijver)
