"""De uitzondering voor een geanonimiseerde HITL-regel heeft DRIE voorwaarden (AVG C).

`HashChainVerifier._verify_bound_evidence` meldt een HITL-regel waarvan de binding niet meer klopt als
fout (`False`). Een regel die bij het opheffen van een tenant is geanonimiseerd heeft geen `user_id`
meer en is dan niet meer na te rekenen (`None`, geen manipulatie) -- ALLEEN als alle drie gelden:

1. de tenantrij bestaat niet meer (`tenant_bestaat is False`),
2. `user_id` is leeg,
3. `event_metadata["geanonimiseerd"]` is `True`.

Elke test hier breekt precies een voorwaarde en eist dat de gewijzigde binding dan WEL als fout wordt
gemeld. Mutatiebewijs (2026-10-12): een voorwaarde uit de code halen maakt de bijbehorende test rood.
De integratietests in `tests/integration/test_avg_auditlog_zonder_persoonsgegevens.py` bewijzen dat
NIET voor voorwaarde 2 en 3, want de aanroeper (`verify_entry`) filtert daar al op voor; vandaar
deze directe toets op de beslisfunctie.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.hitl_evidence import build_resource
from src.core.governance.models import AuditLog

TOOL = "send_payment_reminder"
GEWIJZIGDE_TOOL = "andere_tool"


def _regel(*, user_id: int | None, markering: bool) -> AuditLog:
    """Een HITL-regel waarvan de binding is gebouwd voor user 7, maar waarvan de tool is gewijzigd."""
    resource = build_resource(ticket_ref="t-1", tool_name=TOOL, user_id=7, binding="b1")
    metadata: dict[str, object] = {"tool_name": GEWIJZIGDE_TOOL, "approval_binding": "b1"}
    if markering:
        metadata["geanonimiseerd"] = True
    return AuditLog(
        tenant_id=1,
        action="approved",
        resource=resource,
        user_id=user_id,
        event_metadata=metadata,
    )


def _verifier() -> HashChainVerifier:
    return HashChainVerifier(MagicMock())


def test_all_three_conditions_make_the_row_unverifiable_not_tampered() -> None:
    regel = _regel(user_id=None, markering=True)

    assert _verifier()._verify_bound_evidence(regel, tenant_bestaat=False) is None


def test_an_existing_tenant_is_still_checked() -> None:
    regel = _regel(user_id=None, markering=True)

    assert _verifier()._verify_bound_evidence(regel, tenant_bestaat=True) is False


def test_an_unknown_tenant_state_is_still_checked() -> None:
    """Zonder expliciete `False` (zoals de oude aanroepen) geldt de uitzondering nooit."""
    regel = _regel(user_id=None, markering=True)

    assert _verifier()._verify_bound_evidence(regel) is False


def test_a_kept_user_id_is_still_checked_even_on_a_gone_tenant() -> None:
    regel = _regel(user_id=7, markering=True)

    assert _verifier()._verify_bound_evidence(regel, tenant_bestaat=False) is False


def test_a_missing_marker_is_still_checked_even_on_a_gone_tenant() -> None:
    regel = _regel(user_id=None, markering=False)

    assert _verifier()._verify_bound_evidence(regel, tenant_bestaat=False) is False


def test_the_marker_must_be_literally_true() -> None:
    regel = _regel(user_id=None, markering=False)
    regel.event_metadata = {**(regel.event_metadata or {}), "geanonimiseerd": "ja"}

    assert _verifier()._verify_bound_evidence(regel, tenant_bestaat=False) is False
