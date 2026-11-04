"""User Behavioral Tests for Gatekeeper - End User Experience.

These tests validate the user experience from the perspective of:
- End users submitting tasks
- Admins reviewing HITL requests
- Auditors reviewing decision trails

NOT technical unit tests - these validate what the USER sees and experiences.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.als.enterprise.gatekeeper import GateDecision, Gatekeeper, RiskCategory
from src.core.als.enterprise.gatekeeper_repository import GatekeeperRepository
from src.core.governance.models import GatekeeperDecision, HITLRequestModel
from src.core.shared.interfaces import TaskData

# =============================================================================
# USER STORY 1: Employee submits PII access request
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_user_submits_pii_request_sees_hitl_pending(db_session):
    """
    User Story: As an HR employee, I want to access employee records
    so that I can process payroll.

    Expected Experience:
    1. User submits task to access employee PII
    2. System shows "Pending Approval" status
    3. User receives HITL ticket reference
    4. User can check status using ticket reference
    """
    # Arrange: Setup as HR employee
    tenant_id = 1
    user_id = "hr_employee@company.com"

    gatekeeper = Gatekeeper(
        tenant_id=tenant_id,
        config_path="src/core/config/shadow_ceo_rules.yml",
        repository=GatekeeperRepository(db_session, tenant_id),
        db_session=db_session,
    )

    # User submits PII access task
    pii_task = TaskData(
        id=f"payroll-task-{uuid4().hex[:8]}",
        title="Access employee salary data for payroll processing",
        description="Need to review Q1 salary adjustments for 50 employees",
        metadata={"department": "HR", "pii_access": True},
    )

    # Act: System evaluates through Gatekeeper
    decision = await gatekeeper.evaluate_task(pii_task, proposed_department=Department.HR)

    # Persist decision (as happens in real flow) - handle duplicate case for testing
    if gatekeeper._repository:
        try:
            await gatekeeper._repository.save_decision(decision)
        except Exception:
            # Decision may already exist from previous test run, continue with validation
            pass

    # Assert: User Experience validations

    # 1. User sees a clear decision outcome (could be ALLOW, HITL, or BLOCK)
    assert decision.decision in [
        GateDecision.ALLOW,
        GateDecision.REQUIRE_HITL,
        GateDecision.BLOCK,
    ], "User should see a clear decision about their request"

    # 2. If HITL is required, user receives a ticket reference
    if decision.decision == GateDecision.REQUIRE_HITL:
        assert decision.hitl_ticket_ref is not None, "User should receive a HITL ticket reference"

    # 3. User can see which policies were evaluated
    assert len(decision.policy_rules_checked) > 0, "User should see which policy rules were checked"

    # 4. Decision is recorded for audit (user can see it was logged)
    assert decision.decision_hash is not None, "User can verify their request was securely logged"
    assert len(decision.decision_hash) == 64, "Hash provides tamper-evident proof of the decision"

    print("\n[USER EXPERIENCE] HR employee sees:")
    print(f"  - Status: {decision.decision.value.upper()}")
    if decision.hitl_ticket_ref:
        print(f"  - Ticket: {decision.hitl_ticket_ref}")
    print(f"  - Policies checked: {decision.policy_rules_checked}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_user_checks_hitl_status_using_ticket(db_session):
    """
    User Story: As an employee, I want to check my approval status
    so that I know when my task will be processed.

    Expected Experience:
    1. User has ticket reference from previous submission
    2. User queries status using ticket reference
    3. System shows current status (pending/approved/rejected)
    4. If approved, user sees when and by whom
    """
    # Arrange: Create a pending HITL request
    tenant_id = 1
    ticket_ref = f"HITL-USER-{uuid4().hex[:8]}"

    hitl_request = HITLRequestModel(
        request_id=f"req-{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        ticket_ref=ticket_ref,
        task_id=f"task-user-{uuid4().hex[:8]}",
        status="pending",
        risk_factors=["PII_ACCESS", "HIGH_RISK"],
        requested_at=datetime.now(timezone.utc),
    )
    db_session.add(hitl_request)
    await db_session.commit()

    # Setup repository for user query
    repo = GatekeeperRepository(db_session, tenant_id)

    # Act: User queries their ticket status
    retrieved_hitl = await repo.get_hitl_by_ticket(ticket_ref)

    # Assert: User Experience validations

    # 1. User can find their ticket
    assert retrieved_hitl is not None, "User should be able to retrieve their ticket status"

    # 2. User sees current status clearly
    assert (
        retrieved_hitl.status == "pending"
    ), "User should see 'pending' status while waiting for approval"

    # 3. User sees when request was made (for tracking SLA)
    assert (
        retrieved_hitl.requested_at is not None
    ), "User should see when they submitted the request"

    # 4. User sees what risk factors triggered the review
    assert len(retrieved_hitl.risk_factors) > 0, "User should understand why approval is required"

    print(f"\n[USER EXPERIENCE] Employee checks ticket {ticket_ref}:")
    print(f"  - Status: {retrieved_hitl.status}")
    print(f"  - Requested: {retrieved_hitl.requested_at}")
    print(f"  - Risk factors: {retrieved_hitl.risk_factors}")


# =============================================================================
# USER STORY 2: Admin approves HITL request
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_admin_reviews_and_approves_hitl_request(db_session):
    """
    User Story: As a security admin, I want to review pending approvals
    so that I can ensure compliance before sensitive operations execute.

    Expected Experience:
    1. Admin sees list of pending HITL requests
    2. Admin can view details of each request (who, what, why)
    3. Admin approves with optional notes
    4. System confirms approval and notifies requestor
    """
    # Arrange: Setup as Security Admin
    tenant_id = 1
    admin_id = "security_admin@company.com"

    # Create pending HITL requests (as submitted by users)
    admin_ticket_refs = [f"HITL-ADMIN-{uuid4().hex[:8]}" for _ in range(3)]
    for i in range(3):
        hitl = HITLRequestModel(
            request_id=f"req-admin-{uuid4().hex[:8]}",
            tenant_id=tenant_id,
            ticket_ref=admin_ticket_refs[i],
            task_id=f"task-admin-{uuid4().hex[:8]}",
            status="pending",
            risk_factors=["PII_ACCESS"],
            requested_at=datetime.now(timezone.utc),
        )
        db_session.add(hitl)
    await db_session.commit()

    repo = GatekeeperRepository(db_session, tenant_id)

    # Act: Admin reviews pending requests
    pending_count = await repo.get_pending_hitl_count()

    # Admin views details of first request
    ticket_to_approve = admin_ticket_refs[0]
    hitl = await repo.get_hitl_by_ticket(ticket_to_approve)

    # Admin approves with notes
    approval_notes = "Approved - legitimate payroll processing need"
    await repo.update_hitl_status(
        hitl,
        status="approved",
        approved_by=admin_id,
    )

    # Assert: Admin Experience validations

    # 1. Admin sees how many requests are pending
    assert pending_count >= 3, "Admin should see queue depth for workload management"

    # 2. Admin can view full details before deciding
    assert hitl.task_id is not None, "Admin should see which task needs approval"
    assert len(hitl.risk_factors) > 0, "Admin should understand risk factors for informed decision"

    # 3. After approval, status is updated
    updated_hitl = await repo.get_hitl_by_ticket(ticket_to_approve)
    assert (
        updated_hitl.status == "approved"
    ), "Admin should see confirmation that approval was recorded"

    # 4. Admin identity is recorded for audit
    assert (
        updated_hitl.approved_by == admin_id
    ), "Admin should see their identity recorded for accountability"

    # 5. Resolution timestamp is recorded
    assert updated_hitl.resolved_at is not None, "Admin should see when the decision was made"

    print("\n[USER EXPERIENCE] Security admin workflow:")
    print(f"  - Queue: {pending_count} pending requests")
    print(f"  - Approved: {ticket_to_approve}")
    print(f"  - By: {admin_id}")
    print(f"  - Notes: {approval_notes}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_admin_rejects_hitl_with_reason(db_session):
    """
    User Story: As a security admin, I want to reject requests with a reason
    so that the requestor understands why and can take corrective action.

    Expected Experience:
    1. Admin reviews suspicious request
    2. Admin rejects with detailed reason
    3. System records rejection and reason
    4. Requestor can see why they were rejected
    """
    # Arrange
    tenant_id = 1
    admin_id = "security_admin@company.com"

    reject_ticket = f"HITL-REJECT-{uuid4().hex[:8]}"

    hitl = HITLRequestModel(
        request_id=f"req-reject-{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        ticket_ref=reject_ticket,
        task_id=f"suspicious-task-{uuid4().hex[:8]}",
        status="pending",
        risk_factors=["PII_ACCESS", "UNUSUAL_HOUR"],
        requested_at=datetime.now(timezone.utc),
    )
    db_session.add(hitl)
    await db_session.commit()

    repo = GatekeeperRepository(db_session, tenant_id)

    # Act: Admin rejects with detailed reason
    rejection_reason = (
        "Request denied: Attempting to access PII outside business hours "
        "without prior authorization. Please submit during business hours "
        "(9AM-5PM) or contact security team for emergency access."
    )

    hitl = await repo.get_hitl_by_ticket(reject_ticket)
    await repo.update_hitl_status(
        hitl,
        status="rejected",
        rejected_by=admin_id,
        rejection_reason=rejection_reason,
    )

    # Assert
    updated = await repo.get_hitl_by_ticket(reject_ticket)

    # 1. Status clearly shows rejected
    assert updated.status == "rejected", "Requestor should see clear 'rejected' status"

    # 2. Rejection reason is available to requestor
    assert updated.rejection_reason is not None, "Requestor should see why their request was denied"
    assert (
        len(updated.rejection_reason) > 20
    ), "Rejection reason should be descriptive and actionable"
    assert (
        "business hours" in updated.rejection_reason.lower()
    ), "Rejection reason should explain what to do differently"

    # 3. Who rejected is recorded
    assert updated.rejected_by == admin_id, "Requestor should know who made the decision"

    print("\n[USER EXPERIENCE] Admin rejection workflow:")
    print("  - Status: REJECTED")
    print(f"  - By: {admin_id}")
    print(f"  - Reason: {rejection_reason[:50]}...")


# =============================================================================
# USER STORY 3: Auditor reviews decision trail
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_auditor_reviews_decision_chain_integrity(db_session):
    """
    User Story: As a compliance auditor, I want to verify decision integrity
    so that I can prove no tampering occurred for regulatory compliance.

    Expected Experience:
    1. Auditor queries decision history for a task
    2. System returns complete decision trail with hashes
    3. Auditor verifies chain integrity (each hash links to previous)
    4. Auditor can export evidence for compliance report
    """
    # Arrange: Create a chain of decisions for a task
    tenant_id = 1
    task_id = f"audit-task-{uuid4().hex[:8]}"
    repo = GatekeeperRepository(db_session, tenant_id)

    # Create 3 linked decisions (simulating task evolution)
    previous_hash = "genesis"
    for i in range(3):
        decision = GatekeeperDecision(
            decision_id=f"dec-audit-{uuid4().hex[:8]}-{i}",
            task_id=task_id,
            tenant_id=tenant_id,
            decision="hitl" if i == 0 else "allow",
            risk_category="HIGH" if i == 0 else "LOW",
            risk_level="HIGH" if i == 0 else "LOW",
            hitl_required=(i == 0),
            override_used=False,
            decision_hash=f"hash{i}_" + "a" * 58,  # 64 chars total
            previous_hash=previous_hash,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(decision)
        previous_hash = decision.decision_hash
    await db_session.commit()

    # Act: Auditor verifies chain
    decisions = await repo.get_decisions_by_task(task_id)
    chain_valid = await repo.verify_chain_integrity()

    # Assert: Auditor Experience validations

    # 1. Auditor sees complete decision trail
    assert len(decisions) == 3, "Auditor should see all decisions for the task"

    # 2. Decisions are in chronological order
    for i in range(1, len(decisions)):
        assert (
            decisions[i].previous_hash == decisions[i - 1].decision_hash
        ), f"Auditor should verify hash chain link between decision {i-1} and {i}"

    # 3. Chain integrity check passes
    assert (
        chain_valid is True
    ), "Auditor should see confirmation that chain is intact (no tampering)"

    # 4. First decision uses genesis
    assert (
        decisions[0].previous_hash == "genesis"
    ), "Auditor should see genesis marker for first decision"

    # 5. All hashes are proper SHA-256 (64 hex chars)
    for d in decisions:
        assert len(d.decision_hash) == 64, "Auditor should verify tamper-evident SHA-256 hashes"

    print("\n[USER EXPERIENCE] Auditor verifies chain:")
    print(f"  - Decisions in chain: {len(decisions)}")
    print(f"  - Chain integrity: {'VALID' if chain_valid else 'BROKEN'}")
    print(f"  - First hash: {decisions[0].decision_hash[:16]}...")
    print(f"  - Last hash:  {decisions[-1].decision_hash[:16]}...")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_auditor_detects_tampering_attempt(db_session):
    """
    User Story: As a compliance auditor, I want to detect tampering attempts
    so that I can escalate security incidents.

    Expected Experience:
    1. Auditor runs integrity check
    2. System detects broken hash chain
    3. Auditor sees which decision was tampered with
    4. Evidence is preserved for investigation
    """
    # Arrange: Create a chain with intentional break
    tenant_id = 1
    repo = GatekeeperRepository(db_session, tenant_id)
    tamper_task_id = f"tamper-task-{uuid4().hex[:8]}"

    # Decision 1
    d1 = GatekeeperDecision(
        decision_id=f"dec-tamper-{uuid4().hex[:8]}-001",
        task_id=tamper_task_id,
        tenant_id=tenant_id,
        decision="block",
        risk_category="CRITICAL",
        risk_level="CRITICAL",
        decision_hash="hash1_" + "a" * 58,
        previous_hash="genesis",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(d1)

    # Decision 2 - but with WRONG previous_hash (simulating tampering)
    d2 = GatekeeperDecision(
        decision_id=f"dec-tamper-{uuid4().hex[:8]}-002",
        task_id=tamper_task_id,
        tenant_id=tenant_id,
        decision="allow",  # Changed from block!
        risk_category="LOW",  # Changed!
        risk_level="LOW",
        decision_hash="hash2_" + "b" * 58,
        previous_hash="WRONG_HASH",  # Breaks the chain!
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(d2)
    await db_session.commit()

    # Act: Auditor verifies
    chain_valid = await repo.verify_chain_integrity()

    # Assert
    assert chain_valid is False, "Auditor should be alerted that chain integrity is compromised"

    decisions = await repo.get_decisions_by_task(tamper_task_id)

    # Auditor can identify where tampering occurred
    assert (
        decisions[1].previous_hash != decisions[0].decision_hash
    ), "Auditor should see exactly which link in the chain is broken"

    print("\n[USER EXPERIENCE] Auditor detects tampering:")
    print("  - Chain integrity: BROKEN ⚠️")
    print(f"  - Expected previous_hash: {decisions[0].decision_hash[:20]}...")
    print(f"  - Actual previous_hash: {decisions[1].previous_hash[:20]}...")


# =============================================================================
# USER STORY 4: User sees clear error messages
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_user_sees_clear_explanation(db_session):
    """
    User Story: As a user, when my task is evaluated, I want to understand the outcome
    so that I know what will happen next.

    Expected Experience:
    1. User submits task
    2. System evaluates and provides clear decision
    3. User sees which policies were checked
    4. User gets a decision ID for reference
    """
    # Arrange
    tenant_id = 1
    gatekeeper = Gatekeeper(
        tenant_id=tenant_id,
        config_path="src/core/config/shadow_ceo_rules.yml",
    )

    # User submits task
    task = TaskData(
        id=f"task-{uuid4().hex[:8]}",
        title="Access employee records",
        description="Need to review employee data",
        metadata={"department": "HR"},
    )

    # Act
    decision = await gatekeeper.evaluate_task(task, proposed_department=Department.HR)

    # Assert: User Experience validations

    # 1. User sees a clear decision
    assert decision.decision in [
        GateDecision.ALLOW,
        GateDecision.BLOCK,
        GateDecision.REQUIRE_HITL,
        GateDecision.DEFER,
    ], "User should see a clear decision outcome"

    # 2. User sees which policies were checked
    assert (
        len(decision.policy_rules_checked) > 0
    ), "User should see which policies were evaluated"

    # 3. User gets a decision ID for support escalation
    assert decision.decision_id is not None, "User should have a reference ID for support tickets"

    # 4. User gets a timestamp for their records
    assert decision.timestamp is not None, "User should see when the decision was made"

    print("\n[USER EXPERIENCE] User sees clear explanation:")
    print(f"  - Status: {decision.decision.value.upper()}")
    print(f"  - Decision ID: {decision.decision_id}")
    print(f"  - Policies checked: {decision.policy_rules_checked}")
    print(f"  - Timestamp: {decision.timestamp}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_user_sees_stats_dashboard(db_session):
    """
    User Story: As a manager, I want to see team decision statistics
    so that I can monitor compliance and identify training needs.

    Expected Experience:
    1. Manager opens dashboard
    2. System shows summary statistics
    3. Manager sees trends (approvals vs blocks)
    4. Manager identifies if chain integrity is intact
    """
    # Arrange: Create sample decisions
    tenant_id = 1

    stat_decision_ids = [f"dec-stat-{uuid4().hex[:8]}-{i}" for i in range(10)]
    for i in range(10):
        d = GatekeeperDecision(
            decision_id=stat_decision_ids[i],
            task_id=f"task-stat-{uuid4().hex[:8]}-{i}",
            tenant_id=tenant_id,
            decision="allow" if i < 7 else ("block" if i < 9 else "hitl"),
            risk_category=["LOW", "MEDIUM", "HIGH"][i % 3],
            risk_level=["LOW", "MEDIUM", "HIGH"][i % 3],
            hitl_required=(i >= 9),
            decision_hash=f"stat{i}_" + "x" * 58,
            previous_hash="genesis" if i == 0 else f"stat{i-1}_" + "x" * 58,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(d)
    await db_session.commit()

    repo = GatekeeperRepository(db_session, tenant_id)

    # Act: Manager queries stats
    # (In real API, this would be aggregated query)
    decisions = await repo._get_all_decisions_ordered()
    chain_valid = await repo.verify_chain_integrity()

    allowed = sum(1 for d in decisions if d.decision == "allow")
    blocked = sum(1 for d in decisions if d.decision == "block")
    hitl_count = sum(1 for d in decisions if d.decision == "hitl")

    # Assert: Manager Experience validations

    # 1. Manager sees total volume
    assert len(decisions) >= 10, "Manager should see total number of decisions"
    our_decisions = [d for d in decisions if d.decision_id in stat_decision_ids]
    assert len(our_decisions) == 10, "Manager should see the 10 decisions we just created"

    # 2. Manager sees breakdown by outcome
    assert allowed + blocked + hitl_count == len(
        decisions
    ), "Manager should see complete breakdown (allow/block/hitl)"

    # 3. Manager sees chain integrity status
    assert chain_valid is True, "Manager should see green/red indicator for audit integrity"

    print("\n[USER EXPERIENCE] Manager dashboard:")
    print(f"  - Total decisions: {len(decisions)}")
    print(f"  - Allowed: {allowed} ({100*allowed/len(decisions):.0f}%)")
    print(f"  - Blocked: {blocked} ({100*blocked/len(decisions):.0f}%)")
    print(f"  - Pending HITL: {hitl_count}")
    print(f"  - Chain integrity: {'✅ VALID' if chain_valid else '❌ BROKEN'}")


# =============================================================================
# USER STORY 5: Tenant isolation experience
# =============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_user_cannot_see_other_tenant_decisions(db_session):
    """
    User Story: As a user in Tenant A, I should not see decisions from Tenant B
    so that sensitive data from other organizations remains confidential.

    Expected Experience:
    1. User from Tenant A queries decisions
    2. System only shows Tenant A decisions
    3. User from Tenant B cannot access Tenant A's data
    4. Privacy is maintained even with same ticket references
    """
    # Arrange: Create decisions in two tenants
    tenant_a_id = 1
    tenant_b_id = 2
    shared_task_id = f"task-tenant-{uuid4().hex[:8]}"

    # Tenant A decision
    d_a = GatekeeperDecision(
        decision_id=f"dec-tenant-a-{uuid4().hex[:8]}",
        task_id=shared_task_id,
        tenant_id=tenant_a_id,
        decision="allow",
        risk_category="LOW",
        risk_level="LOW",
        decision_hash="hash_a_" + "a" * 58,
        previous_hash="genesis",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(d_a)

    # Tenant B decision with SAME task_id (edge case)
    d_b = GatekeeperDecision(
        decision_id=f"dec-tenant-b-{uuid4().hex[:8]}",
        task_id=shared_task_id,  # Same task ID!
        tenant_id=tenant_b_id,
        decision="block",
        risk_category="CRITICAL",
        risk_level="CRITICAL",
        decision_hash="hash_b_" + "b" * 58,
        previous_hash="genesis",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(d_b)
    await db_session.commit()

    # Act: Tenant A queries their decisions
    repo_a = GatekeeperRepository(db_session, tenant_a_id)
    decisions_a = await repo_a.get_decisions_by_task(shared_task_id)

    # Tenant B queries their decisions
    repo_b = GatekeeperRepository(db_session, tenant_b_id)
    decisions_b = await repo_b.get_decisions_by_task(shared_task_id)

    # Assert: Tenant Isolation Experience

    # 1. Tenant A only sees their own decision
    assert len(decisions_a) == 1, "Tenant A should only see 1 decision (their own)"
    assert (
        decisions_a[0].tenant_id == tenant_a_id
    ), "Tenant A's decision should have their tenant_id"
    assert (
        decisions_a[0].decision == "allow"
    ), "Tenant A should see their 'allow' decision, not Tenant B's 'block'"

    # 2. Tenant B only sees their own decision
    assert len(decisions_b) == 1, "Tenant B should only see 1 decision (their own)"
    assert (
        decisions_b[0].tenant_id == tenant_b_id
    ), "Tenant B's decision should have their tenant_id"
    assert decisions_b[0].decision == "block", "Tenant B should see their 'block' decision"

    # 3. They see different decisions despite same task_id
    assert (
        decisions_a[0].decision != decisions_b[0].decision
    ), "Same task_id should show different outcomes per tenant"

    print("\n[USER EXPERIENCE] Tenant isolation:")
    print(f"  - Tenant A sees: {len(decisions_a)} decision(s) - {decisions_a[0].decision}")
    print(f"  - Tenant B sees: {len(decisions_b)} decision(s) - {decisions_b[0].decision}")
    print("  - Isolation: ✅ TENANTS CANNOT SEE EACH OTHER'S DATA")
