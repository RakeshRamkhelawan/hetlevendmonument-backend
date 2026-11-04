"""
Integration test for hash integrity and tamper detection.
"""

import hashlib
import json
from datetime import timedelta
import pytest
from sqlalchemy import text
from src.core.copilot.audit.report_generator import AuditReportGenerator
from src.core.copilot.council.audit_writer import CouncilAuditWriter
from tests.integration.copilot.conftest import make_proposal, seed_tenants

@pytest.mark.asyncio
async def test_audit_report_detects_content_tampering(db_session, real_council):
    # 1. Setup
    await seed_tenants(db_session, [801])
    
    proposal = make_proposal(
        tenant_id=801,
        user_id=1,
        action_type="local__send_email",
        action_params={"to": "user@example.com", "body": "Original body"},
        message="I've sent the email.",
        reasoning="User requested email sending."
    )
    
    # 2. Deliberate and Persist (via Council)
    decision = await real_council.deliberate(proposal)
    assert decision.verdict.value in ["approved", "modified"]
    
    # 3. Verify initially (should be valid)
    generator = AuditReportGenerator(db_session)
    # Wide range to avoid precision issues
    summary, decisions = await generator._build_summary(
        tenant_id=801,
        from_date=decision.timestamp - timedelta(minutes=1),
        to_date=decision.timestamp + timedelta(minutes=1)
    )
    assert len(decisions) > 0
    assert summary.hash_chain_valid is True
    assert decisions[0]["integrity_valid"] is True

    # 4. TAMPER: Manually modify action_params in the database
    await db_session.execute(
        text("UPDATE council_decisions SET action_params = :new_params WHERE decision_id = :id"),
        {
            "new_params": json.dumps({"to": "hacker@evil.com", "body": "Original body"}),
            "id": decision.decision_id
        }
    )
    await db_session.commit()
    
    # 5. Verify after tampering (should be INVALID)
    summary_tampered, decisions_tampered = await generator._build_summary(
        tenant_id=801,
        from_date=decision.timestamp - timedelta(minutes=1),
        to_date=decision.timestamp + timedelta(minutes=1)
    )
    
    assert summary_tampered.hash_chain_valid is False
    assert decisions_tampered[0]["integrity_valid"] is False
    assert decisions_tampered[0]["decision_id"] == str(decision.decision_id)
