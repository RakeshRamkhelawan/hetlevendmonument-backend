import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import select

from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow
from src.core.governance.retention_cleanup import _cleanup_council_decisions_async


async def _insert_with_timestamp(db_session, ts: datetime, tenant_id: int = 1):
    decision_id = str(uuid.uuid4())
    row = CouncilDecisionRow(
        decision_id=decision_id,
        proposal_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=1,
        timestamp=ts,
        verdict="APPROVE",
        trigger="USER_REQUEST",
        confidence=1.0,
        action_type="test",
        action_params={"key": "value"},
        message="test",
        data_classification="internal",
        model_id="test",
        model_version="v1",
        reasoning="test",
        explanation_for_user="test",
        deliberation_ms=10,
        officer_verdicts_hash="dummy_verdicts_hash",
        decision_hash=str(uuid.uuid4())[:64],
        previous_decision_hash=None,
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


async def _exists(db_session, decision_id: UUID) -> bool:
    result = await db_session.execute(
        select(CouncilDecisionRow).where(CouncilDecisionRow.decision_id == decision_id)
    )
    return result.scalar_one_or_none() is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retention_cleanup_deletes_old_decisions(db_session):
    """Decisions ouder dan 395 dagen worden verwijderd, jongere blijven."""
    old_ts = datetime.now(timezone.utc) - timedelta(days=400)
    young_ts = datetime.now(timezone.utc) - timedelta(days=30)

    old_decision = await _insert_with_timestamp(db_session, ts=old_ts)
    young_decision = await _insert_with_timestamp(db_session, ts=young_ts)

    @asynccontextmanager
    async def _mock_db_session():
        yield db_session

    with patch("src.core.governance.retention_cleanup.get_db_session", _mock_db_session):
        await _cleanup_council_decisions_async()

    # Old gone, young stays
    assert await _exists(db_session, old_decision.decision_id) is False
    assert await _exists(db_session, young_decision.decision_id) is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retention_cleanup_cascades_officer_verdicts(db_session):
    """Officer_verdicts cascade-verwijderd bij decision-delete."""
    old_ts = datetime.now(timezone.utc) - timedelta(days=400)
    old_decision = await _insert_with_timestamp(db_session, ts=old_ts)

    # Insert 6 officer_verdicts voor deze decision
    for i in range(6):
        verdict_id = str(uuid.uuid4())
        v_row = OfficerVerdictRow(
            verdict_id=verdict_id,
            decision_id=old_decision.decision_id,
            tenant_id=1,
            officer_name=f"Officer{i}",
            officer_version="1.0.0",
            verdict="APPROVE",
            reason_code="OK",
            reason_text="ok",
            evidence={},
            deliberation_ms=10,
            confidence=0.9,
            used_cache=False,
        )
        db_session.add(v_row)
    await db_session.commit()

    @asynccontextmanager
    async def _mock_db_session():
        yield db_session

    with patch("src.core.governance.retention_cleanup.get_db_session", _mock_db_session):
        await _cleanup_council_decisions_async()

    # Verifieer: 0 officer_verdicts voor deze decision_id
    result = await db_session.execute(
        select(OfficerVerdictRow).where(OfficerVerdictRow.decision_id == old_decision.decision_id)
    )
    verdicts = result.scalars().all()
    assert len(verdicts) == 0
