from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from src.core.tasks.dramatiq_broker import workflow_actor
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.copilot.council.models import CouncilDecisionRow
from src.core.governance.services.audit_service import AuditService
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class _ContestProxy:
    """Lightweight return object for submit_contest."""

    def __init__(self, contest_id: uuid.UUID, submitted_at: datetime) -> None:
        self.contest_id = contest_id
        self.status = "pending"
        self.submitted_at = submitted_at
        #: "verzonden" of "mislukt": of de melding aan de beheerders de wachtrij in is gegaan. Het bezwaar zelf is
        #: dan al bewaard; alleen de melding kan ontbreken.
        self.admin_notification = "verzonden"


@workflow_actor(queue_name="notifications")
def notify_tenant_admins_of_contest(
    contest_id: str,
    decision_id: str,
    tenant_id: int,
    user_id: int,
    reason_category: str,
) -> None:
    """Notify tenant admins that a decision has been contested."""
    logger.info(
        "Contest notification sent to admins for contest_id=%s decision_id=%s",
        contest_id,
        decision_id,
    )


async def submit_contest(
    db: AsyncSession,
    decision: CouncilDecisionRow,
    user: UserResponse,
    reason_category: str,
    reason_text: str,
) -> _ContestProxy:
    """Persist a contest and enqueue admin notification."""
    contest_id = uuid.uuid4()
    submitted_at = datetime.now(timezone.utc)

    await db.execute(
        text(
            """
            INSERT INTO decision_contests (
                contest_id, decision_id, tenant_id, user_id,
                submitted_at, reason_category, reason_text, status
            ) VALUES (
                :contest_id, :decision_id, :tenant_id, :user_id,
                :submitted_at, :reason_category, :reason_text, 'pending'
            )
            """
        ),
        {
            "contest_id": str(contest_id),
            "decision_id": str(decision.decision_id),
            "tenant_id": decision.tenant_id,
            "user_id": user.id,
            "submitted_at": submitted_at,
            "reason_category": reason_category,
            "reason_text": reason_text,
        },
    )
    decision_id = str(decision.decision_id)
    tenant_id = decision.tenant_id
    user_id = user.id

    await db.commit()

    # VIA AuditService, NIET met rauwe SQL (ADR-036 OP-108).
    #
    # De vorige INSERT liet `audit_hash` EN `previous_hash` leeg. `verify_chain` liep daar stuk
    # op de link-controle en bekeek daarna niets meer, dus een tenant die ooit een besluit had
    # aangevochten had vanaf dat moment een onverifieerbare keten. `log_event` vult de keten wel,
    # onder hetzelfde per-tenant advisory lock als alle andere schrijvers.
    #
    # Beide commits blijven staan. De eerste (hierboven) omdat `best_effort` de HELE sessie
    # terugrolt: zonder die commit zou een falende auditregel de contest-INSERT meenemen. De
    # tweede omdat `log_event` alleen `flush()` doet -- zonder commit is de auditregel niet
    # duurzaam. Zelfde volgorde als `hitl_router._write_audit_entry`.
    async with best_effort("contest audit log", db_session=db):
        await AuditService.log_event(
            db=db,
            event_type="governance",
            severity="low",
            source_ip="0.0.0.0",  # nosec B104: systeemhandeling, geen clientverzoek
            endpoint="/copilot/audit/contest",
            description=f"User {user_id} contested decision {decision_id}",
            user_id=user_id,
            tenant_id=tenant_id,
            action="contest_submitted",
            resource=f"council_decision:{decision_id}",
        )
        await db.commit()

    bezwaar = _ContestProxy(contest_id, submitted_at)
    try:
        notify_tenant_admins_of_contest.send(
            str(contest_id),
            decision_id,
            tenant_id,
            user_id,
            reason_category,
        )
    except Exception as exc:
        # Het bezwaar is van de klant en staat al in de database (commit hierboven). Een 500 zou de klant een
        # duplicaat laten indienen; daarom GEEN fout, maar een eerlijk antwoord dat de melding aan de beheerders
        # niet is verstuurd (ADR-036 OP-13: `.send()` faalt zichtbaar als Redis weg is).
        logger.error(
            "Melding aan de beheerders over bezwaar %s niet verstuurd: %s: %s",
            contest_id,
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": tenant_id},
        )
        bezwaar.admin_notification = "mislukt"

    return bezwaar
